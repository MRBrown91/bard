"""Tests for the document API endpoints.

These cover transport, error translation, and the rules the application layer
relies on: session scoping, indistinguishable 404s, and the metadata fields a
caller may not repoint. Repositories are stubbed, so the database-side rules
(campaign scoping, cascade stamping, statement ordering) are covered in
``test_document_repo.py``.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_campaign,
    get_document_repo,
    get_session_repo,
)
from app.application.exceptions import NotFoundError, ValidationError
from app.main import app
from app.models import Campaign, Document, DocumentStatement
from app.models import Session as PlaySession
from app.repositories import DocumentRepository, SessionRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)

BASE = "/api/campaigns/{campaign_id}/documents"


def make_campaign() -> Campaign:
    """Build a campaign owned by an arbitrary user."""
    return Campaign(
        id=uuid4(),
        user_id=uuid4(),
        name="The Long Road",
        description=None,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
    )


def make_document(
    campaign: Campaign,
    *,
    document_id: UUID | None = None,
    session_id: UUID | None = None,
    document_type: str = "lore",
    title: str = "On the Salt Road",
    content: str = "The caravan left at dawn.",
    statements: list[DocumentStatement] | None = None,
) -> Document:
    """Build a document with optional statements."""
    return Document(
        id=document_id or uuid4(),
        campaign_id=campaign.id,
        session_id=session_id,
        document_type=document_type,
        title=title,
        content=content,
        source_type="player_note",
        source_reference="p.12",
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
        statements=statements if statements is not None else [],
    )


def make_statement(
    document_id: UUID,
    position: int,
    content: str = "A fact from the source.",
    *,
    created_at: datetime = NOW,
) -> DocumentStatement:
    """Build a statement row."""
    return DocumentStatement(
        id=uuid4(),
        document_id=document_id,
        position=position,
        content=content,
        created_at=created_at,
        updated_at=created_at,
        deleted_at=None,
    )


@dataclass
class Harness:
    """Stubbed repositories plus a client."""

    client: TestClient
    campaign: Campaign
    documents: AsyncMock
    sessions: AsyncMock

    @property
    def url(self) -> str:
        return BASE.format(campaign_id=self.campaign.id)


def override_repository(repo: AsyncMock) -> Any:
    """Build a dependency override returning a fixed repository."""

    def dependency() -> AsyncMock:
        return repo

    return dependency


@contextmanager
def authorized() -> Iterator[Harness]:
    """Override campaign scope and the document and session repositories."""
    campaign = make_campaign()
    documents = AsyncMock(spec=DocumentRepository)
    documents.session = AsyncMock(spec=AsyncSession)
    documents.campaign_id = campaign.id
    sessions = AsyncMock(spec=SessionRepository)
    sessions.session = AsyncMock(spec=AsyncSession)
    sessions.campaign_id = campaign.id

    app.dependency_overrides[get_document_repo] = override_repository(documents)
    app.dependency_overrides[get_session_repo] = override_repository(sessions)

    def current_campaign() -> Campaign:
        return campaign

    app.dependency_overrides[get_current_campaign] = current_campaign
    try:
        yield Harness(TestClient(app), campaign, documents, sessions)
    finally:
        app.dependency_overrides.clear()


CREATE_BODY: dict[str, Any] = {
    "document_type": "lore",
    "title": "On the Salt Road",
    "content": "The caravan left at dawn.",
    "source_type": "player_note",
    "source_reference": "p.12",
}


class TestCreate:
    """POST /documents."""

    def test_creates_and_returns_201(self) -> None:
        with authorized() as h:
            document = make_document(h.campaign)
            h.documents.create.return_value = document
            response = h.client.post(h.url, json=CREATE_BODY)
            assert response.status_code == 201
            body = response.json()
            assert body["title"] == "On the Salt Road"
            assert body["campaign_id"] == str(h.campaign.id)

    def test_rejects_a_campaign_in_the_body(self) -> None:
        """The campaign comes from the authorized scope, not the request.

        ``extra="forbid"`` rejects it outright rather than ignoring it, so a
        caller cannot believe they moved a document between campaigns.
        """
        with authorized() as h:
            response = h.client.post(
                h.url, json={**CREATE_BODY, "campaign_id": str(uuid4())}
            )
            assert response.status_code == 422
            h.documents.create.assert_not_awaited()

    def test_create_is_never_given_a_campaign(self) -> None:
        """The repository scope supplies the campaign; no kwarg is passed."""
        with authorized() as h:
            h.documents.create.return_value = make_document(h.campaign)
            h.client.post(h.url, json=CREATE_BODY)
            assert h.documents.create.await_args.kwargs.get("campaign_id") is None
            assert h.documents.campaign_id == h.campaign.id

    def test_rejects_unknown_fields(self) -> None:
        """A misspelled field is a 422, not a silently dropped value."""
        with authorized() as h:
            response = h.client.post(h.url, json={**CREATE_BODY, "titel": "typo"})
            assert response.status_code == 422
            h.documents.create.assert_not_awaited()

    @pytest.mark.parametrize("field", ["document_type", "title", "content"])
    def test_requires_the_mandatory_fields(self, field: str) -> None:
        with authorized() as h:
            body = {k: v for k, v in CREATE_BODY.items() if k != field}
            assert h.client.post(h.url, json=body).status_code == 422

    def test_rejects_an_empty_document_type(self) -> None:
        with authorized() as h:
            response = h.client.post(h.url, json={**CREATE_BODY, "document_type": ""})
            assert response.status_code == 422

    def test_accepts_a_free_form_document_type(self) -> None:
        """No vocabulary is defined, so an unrecognised label is allowed."""
        with authorized() as h:
            h.documents.create.return_value = make_document(
                h.campaign, document_type="session-recap-2026-01"
            )
            response = h.client.post(
                h.url, json={**CREATE_BODY, "document_type": "session-recap-2026-01"}
            )
            assert response.status_code == 201

    def test_allows_a_document_without_a_session(self) -> None:
        """A null session_id means campaign-level source material."""
        with authorized() as h:
            h.documents.create.return_value = make_document(h.campaign)
            response = h.client.post(h.url, json=CREATE_BODY)
            assert response.status_code == 201
            assert h.documents.create.await_args.kwargs["session_id"] is None

    def test_accepts_a_session_from_the_same_campaign(self) -> None:
        with authorized() as h:
            session_id = uuid4()
            h.sessions.get.return_value = PlaySession(
                id=session_id,
                campaign_id=h.campaign.id,
                name="Session 1",
                session_number=1,
                started_at=NOW,
                ended_at=None,
                created_at=NOW,
                updated_at=NOW,
                deleted_at=None,
            )
            h.documents.create.return_value = make_document(
                h.campaign, session_id=session_id
            )
            response = h.client.post(
                h.url, json={**CREATE_BODY, "session_id": str(session_id)}
            )
            assert response.status_code == 201

    def test_rejects_a_session_from_another_campaign(self) -> None:
        """The foreign key permits this; the application must not."""
        with authorized() as h:
            session_id = uuid4()
            h.sessions.get.return_value = PlaySession(
                id=session_id,
                campaign_id=uuid4(),
                name="Someone else's session",
                session_number=1,
                started_at=NOW,
                ended_at=None,
                created_at=NOW,
                updated_at=NOW,
                deleted_at=None,
            )
            response = h.client.post(
                h.url, json={**CREATE_BODY, "session_id": str(session_id)}
            )
            assert response.status_code == 422
            assert response.json()["detail"] == "Invalid session_id"
            h.documents.create.assert_not_awaited()

    def test_rejects_a_session_that_does_not_exist(self) -> None:
        with authorized() as h:
            h.sessions.get.return_value = None
            response = h.client.post(
                h.url, json={**CREATE_BODY, "session_id": str(uuid4())}
            )
            assert response.status_code == 422
            h.documents.create.assert_not_awaited()

    def test_missing_and_foreign_sessions_are_indistinguishable(self) -> None:
        """Naming which one it was would confirm the session id is real."""
        with authorized() as h:
            bodies = []
            for resolved in (None, PlaySession(
                id=uuid4(),
                campaign_id=uuid4(),
                name="x",
                session_number=1,
                started_at=NOW,
                ended_at=None,
                created_at=NOW,
                updated_at=NOW,
                deleted_at=None,
            )):
                h.sessions.get.return_value = resolved
                response = h.client.post(
                h.url, json={**CREATE_BODY, "session_id": str(uuid4())}
            )
                assert response.status_code == 422
                bodies.append(response.json())
            assert bodies[0]["detail"] == bodies[1]["detail"]
            assert bodies[0]["code"] == bodies[1]["code"]


class TestList:
    """GET /documents."""

    def test_returns_documents_with_pagination(self) -> None:
        with authorized() as h:
            h.documents.list_filtered.return_value = [make_document(h.campaign)]
            h.documents.count_filtered.return_value = 1
            response = h.client.get(h.url)
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 1
            assert body["page"] == 1
            assert body["total_pages"] == 1
            assert len(body["items"]) == 1

    def test_forwards_the_filters_to_the_repository(self) -> None:
        with authorized() as h:
            session_id = uuid4()
            h.documents.list_filtered.return_value = []
            h.documents.count_filtered.return_value = 0
            h.client.get(
                h.url,
                params={"document_type": "lore", "session_id": str(session_id)},
            )
            kwargs = h.documents.list_filtered.await_args.kwargs
            assert kwargs["document_type"] == "lore"
            assert kwargs["session_id"] == session_id

    def test_count_uses_the_same_predicate_as_the_page(self) -> None:
        """A total from a different query is how P1B.2 reported impossible pages."""
        with authorized() as h:
            h.documents.list_filtered.return_value = [make_document(h.campaign)]
            h.documents.count_filtered.return_value = 7
            body = h.client.get(h.url).json()
            assert body["total"] == 7
            assert body["total_pages"] == 1
            count_kwargs = h.documents.count_filtered.await_args.kwargs
            list_kwargs = h.documents.list_filtered.await_args.kwargs
            assert count_kwargs["document_type"] == list_kwargs["document_type"]
            assert count_kwargs["session_id"] == list_kwargs["session_id"]

    def test_calculates_total_pages_by_rounding_up(self) -> None:
        with authorized() as h:
            h.documents.list_filtered.return_value = []
            h.documents.count_filtered.return_value = 5
            body = h.client.get(h.url, params={"page_size": 2}).json()
            assert body["total_pages"] == 3

    def test_empty_campaign_reports_zero_pages(self) -> None:
        with authorized() as h:
            h.documents.list_filtered.return_value = []
            h.documents.count_filtered.return_value = 0
            body = h.client.get(h.url).json()
            assert body == {
                "items": [],
                "total": 0,
                "page": 1,
                "page_size": 20,
                "total_pages": 0,
            }

    def test_rejects_an_out_of_range_page(self) -> None:
        with authorized() as h:
            assert h.client.get(h.url, params={"page": 0}).status_code == 422
            assert h.client.get(h.url, params={"page_size": 101}).status_code == 422


class TestGet:
    """GET /documents/{document_id}."""

    def test_returns_the_document_with_its_statements(self) -> None:
        with authorized() as h:
            document = make_document(h.campaign)
            document.statements = [
                make_statement(document.id, 0, "First."),
                make_statement(document.id, 1, "Second."),
            ]
            h.documents.get_with_statements.return_value = document
            response = h.client.get(f"{h.url}/{document.id}")
            assert response.status_code == 200
            body = response.json()
            assert [s["content"] for s in body["statements"]] == ["First.", "Second."]

    def test_statements_default_to_empty(self) -> None:
        with authorized() as h:
            h.documents.get_with_statements.return_value = make_document(h.campaign)
            body = h.client.get(f"{h.url}/{uuid4()}").json()
            assert body["statements"] == []

    def test_returns_404_for_a_missing_document(self) -> None:
        with authorized() as h:
            document_id = uuid4()
            h.documents.get_with_statements.return_value = None
            response = h.client.get(f"{h.url}/{document_id}")
            assert response.status_code == 404
            assert response.json()["detail"] == "Document not found"

    def test_404_does_not_disclose_that_the_document_exists_elsewhere(self) -> None:
        with authorized() as h:
            h.documents.get_with_statements.return_value = None
            body = h.client.get(f"{h.url}/{uuid4()}").json()
            assert body["code"] == "NotFoundError"
            assert "campaign" not in body["detail"].lower()

    def test_does_not_expose_deleted_at(self) -> None:
        """Every read filters deleted rows, so the field would always be null."""
        with authorized() as h:
            h.documents.get_with_statements.return_value = make_document(h.campaign)
            assert "deleted_at" not in h.client.get(f"{h.url}/{uuid4()}").json()


class TestUpdate:
    """PATCH /documents/{document_id}."""

    def test_updates_metadata(self) -> None:
        with authorized() as h:
            document = make_document(h.campaign)
            h.documents.get_with_statements.return_value = document
            response = h.client.patch(
                f"{h.url}/{document.id}", json={"title": "Revised"}
            )
            assert response.status_code == 200
            assert response.json()["title"] == "Revised"

    def test_ignores_fields_that_were_not_sent(self) -> None:
        """A PATCH must not blank out fields the caller did not mention."""
        with authorized() as h:
            document = make_document(h.campaign, content="keep me")
            h.documents.get_with_statements.return_value = document
            response = h.client.patch(
                f"{h.url}/{document.id}", json={"title": "New"}
            )
            body = response.json()
            assert body["content"] == "keep me"

    def test_cannot_repoint_the_campaign(self) -> None:
        with authorized() as h:
            document = make_document(h.campaign)
            h.documents.get_with_statements.return_value = document
            response = h.client.patch(
                f"{h.url}/{document.id}", json={"campaign_id": str(uuid4())}
            )
            assert response.status_code == 422
            assert document.campaign_id == h.campaign.id

    def test_revalidates_the_session_when_it_changes(self) -> None:
        with authorized() as h:
            document = make_document(h.campaign)
            h.documents.get_with_statements.return_value = document
            h.sessions.get.return_value = None
            response = h.client.patch(
                f"{h.url}/{document.id}", json={"session_id": str(uuid4())}
            )
            assert response.status_code == 422
            assert response.json()["detail"] == "Invalid session_id"

    def test_does_not_check_the_session_when_it_is_unchanged(self) -> None:
        with authorized() as h:
            document = make_document(h.campaign)
            h.documents.get_with_statements.return_value = document
            response = h.client.patch(f"{h.url}/{document.id}", json={"title": "New"})
            assert response.status_code == 200
            h.sessions.get.assert_not_awaited()

    def test_returns_404_for_a_missing_document(self) -> None:
        with authorized() as h:
            document_id = uuid4()
            h.documents.get_with_statements.return_value = None
            response = h.client.patch(f"{h.url}/{document_id}", json={"title": "x"})
            assert response.status_code == 404

    def test_rejects_an_empty_document_type(self) -> None:
        with authorized() as h:
            h.documents.get_with_statements.return_value = make_document(h.campaign)
            response = h.client.patch(f"{h.url}/{uuid4()}", json={"document_type": ""})
            assert response.status_code == 422


class TestDelete:
    """DELETE /documents/{document_id}."""

    def test_soft_deletes_and_returns_204(self) -> None:
        with authorized() as h:
            h.documents.soft_delete_with_statements.return_value = True
            response = h.client.delete(f"{h.url}/{uuid4()}")
            assert response.status_code == 204
            assert response.content == b""

    def test_returns_404_for_a_missing_document(self) -> None:
        with authorized() as h:
            h.documents.soft_delete_with_statements.return_value = False
            response = h.client.delete(f"{h.url}/{uuid4()}")
            assert response.status_code == 404
            assert response.json()["detail"] == "Document not found"

    def test_cascades_to_statements(self) -> None:
        """The repository call that stamps both rows is the one that runs."""
        with authorized() as h:
            document_id = uuid4()
            h.documents.soft_delete_with_statements.return_value = True
            h.client.delete(f"{h.url}/{document_id}")
            h.documents.soft_delete_with_statements.assert_awaited_once_with(
                document_id
            )
            h.documents.soft_delete.assert_not_awaited()


class TestErrorTranslation:
    """Application errors map to their HTTP status."""

    def test_conflict_maps_to_409(self) -> None:
        from app.application.exceptions import ConflictError

        with authorized() as h:
            h.documents.create.side_effect = ConflictError("nope")
            assert h.client.post(h.url, json=CREATE_BODY).status_code == 409

    def test_not_found_from_the_repository_is_not_swallowed(self) -> None:
        """A repository raising rather than returning None still maps to 404."""
        with authorized() as h:
            h.documents.get_with_statements.side_effect = NotFoundError("gone")
            assert h.client.get(f"{h.url}/{uuid4()}").status_code == 404

    def test_validation_error_maps_to_422(self) -> None:
        with authorized() as h:
            h.documents.create.side_effect = ValidationError("bad")
            assert h.client.post(h.url, json=CREATE_BODY).status_code == 422
