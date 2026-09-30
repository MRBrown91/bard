"""Tests for the document statement API endpoints.

Two things are covered here that the mocked repository tests in
``test_document_repo.py`` cannot be. The first is the write path's campaign
isolation: ``document_statements`` has no ``campaign_id``, so nothing scopes
the insert and the application layer has to prove the parent document is
reachable. The second is that the two ids in the path address one resource, so a
statement id from another document under the same campaign is a 404.
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
    get_document_statement_repo,
)
from app.application.exceptions import ValidationError
from app.main import app
from app.models import Campaign, Document, DocumentStatement
from app.repositories import DocumentRepository, DocumentStatementRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)


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


def make_document(campaign: Campaign, document_id: UUID | None = None) -> Document:
    """Build a document in the given campaign."""
    return Document(
        id=document_id or uuid4(),
        campaign_id=campaign.id,
        session_id=None,
        document_type="lore",
        title="On the Salt Road",
        content="The caravan left at dawn.",
        source_type=None,
        source_reference=None,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
        statements=[],
    )


def make_statement(
    document_id: UUID,
    position: int = 1,
    content: str = "The road forks at Kettle Ford.",
) -> DocumentStatement:
    """Build a statement row under the given document."""
    return DocumentStatement(
        id=uuid4(),
        document_id=document_id,
        position=position,
        content=content,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
    )


@dataclass
class Harness:
    """Stubbed repositories plus a client."""

    client: TestClient
    campaign: Campaign
    documents: AsyncMock
    statements: AsyncMock
    document_id: UUID

    @property
    def url(self) -> str:
        return (
            f"/api/campaigns/{self.campaign.id}"
            f"/documents/{self.document_id}/statements"
        )


def override_repository(repo: AsyncMock) -> Any:
    """Build a dependency override returning a fixed repository."""

    def dependency() -> AsyncMock:
        return repo

    return dependency


@contextmanager
def authorized(*, document_exists: bool = True) -> Iterator[Harness]:
    """Override campaign scope and both repositories.

    ``document_exists=False`` simulates a document that is soft-deleted or
    belongs to another campaign, which the scoped repository reports as a miss.
    """
    campaign = make_campaign()
    document_id = uuid4()

    documents = AsyncMock(spec=DocumentRepository)
    documents.session = AsyncMock(spec=AsyncSession)
    documents.campaign_id = campaign.id
    documents.get.return_value = (
        make_document(campaign, document_id) if document_exists else None
    )

    statements = AsyncMock(spec=DocumentStatementRepository)
    statements.session = AsyncMock(spec=AsyncSession)
    statements.campaign_id = campaign.id

    app.dependency_overrides[get_document_repo] = override_repository(documents)
    app.dependency_overrides[get_document_statement_repo] = override_repository(
        statements
    )
    app.dependency_overrides[get_current_campaign] = lambda: campaign
    try:
        yield Harness(TestClient(app), campaign, documents, statements, document_id)
    finally:
        app.dependency_overrides.clear()


BODY: dict[str, Any] = {"position": 1, "content": "The road forks at Kettle Ford."}


class TestCreate:
    """POST /documents/{id}/statements."""

    def test_creates_and_returns_201(self) -> None:
        with authorized() as h:
            h.statements.create.return_value = make_statement(h.document_id)
            response = h.client.post(h.url, json=BODY)
            assert response.status_code == 201
            body = response.json()
            assert body["content"] == "The road forks at Kettle Ford."
            assert body["document_id"] == str(h.document_id)

    def test_uses_the_document_from_the_path(self) -> None:
        with authorized() as h:
            h.statements.create.return_value = make_statement(h.document_id)
            h.client.post(h.url, json=BODY)
            assert h.statements.create.await_args.kwargs["document_id"] == h.document_id

    def test_rejects_a_document_in_the_body(self) -> None:
        """The document comes from the path; a second one is a client error."""
        with authorized() as h:
            response = h.client.post(
                h.url, json={**BODY, "document_id": str(uuid4())}
            )
            assert response.status_code == 422
            h.statements.create.assert_not_awaited()

    def test_rejects_unknown_fields(self) -> None:
        with authorized() as h:
            response = h.client.post(h.url, json={**BODY, "positon": 2})
            assert response.status_code == 422
            h.statements.create.assert_not_awaited()

    @pytest.mark.parametrize("field", ["position", "content"])
    def test_requires_the_mandatory_fields(self, field: str) -> None:
        with authorized() as h:
            body = {k: v for k, v in BODY.items() if k != field}
            assert h.client.post(h.url, json=body).status_code == 422

    def test_refuses_a_document_the_caller_cannot_reach(self) -> None:
        """The isolation case this endpoint exists to get right.

        ``document_statements`` has no ``campaign_id``, so the insert itself is
        unscoped and the foreign key would accept another campaign's document.
        """
        with authorized(document_exists=False) as h:
            response = h.client.post(h.url, json=BODY)
            assert response.status_code == 404
            assert response.json()["detail"] == "Document not found"
            h.statements.create.assert_not_awaited()

    def test_allows_duplicate_positions(self) -> None:
        """Ties are legitimate; the schema resolves them by created_at, id."""
        with authorized() as h:
            h.statements.create.return_value = make_statement(h.document_id)
            response = h.client.post(h.url, json=BODY)
            assert response.status_code == 201

    def test_accepts_a_negative_position(self) -> None:
        """Ordering is what position means, and negatives still order."""
        with authorized() as h:
            h.statements.create.return_value = make_statement(h.document_id, -5)
            response = h.client.post(h.url, json={**BODY, "position": -5})
            assert response.status_code == 201
            assert response.json()["position"] == -5

    def test_refuses_a_blank_content(self) -> None:
        """Create and update agree: neither stores an empty anchor.

        A statement is what a fact cites, so a blank one is not a lesser
        statement, it is an unverifiable citation. Refusing it on update only
        would leave a hole, since a caller could POST one and then PATCH it.
        """
        with authorized() as h:
            response = h.client.post(h.url, json={**BODY, "content": " "})
            assert response.status_code == 422
            h.statements.create.assert_not_awaited()

    def test_refuses_an_empty_content(self) -> None:
        """The schema rejects "" before the use case is reached."""
        with authorized() as h:
            response = h.client.post(h.url, json={**BODY, "content": ""})
            assert response.status_code == 422
            h.statements.create.assert_not_awaited()

    def test_accepts_content_with_surrounding_whitespace(self) -> None:
        """Padding around real text is preserved, not stripped away.

        The check asks whether the content is *meaningfully* empty. Rewriting
        the caller's text would be a different decision, and the statement is
        provenance that should read as submitted.
        """
        with authorized() as h:
            padded = make_statement(h.document_id, content="  The ford holds.  ")
            h.statements.create.return_value = padded
            response = h.client.post(
                h.url, json={**BODY, "content": "  The ford holds.  "}
            )
            assert response.status_code == 201


class TestList:
    """GET /documents/{id}/statements."""

    def test_returns_statements_in_order(self) -> None:
        with authorized() as h:
            rows = [make_statement(h.document_id, i) for i in (3, 1, 2)]
            h.statements.list_filtered.return_value = rows
            h.statements.count_by_document.return_value = 3
            response = h.client.get(h.url)
            assert response.status_code == 200
            body = response.json()
            assert [item["position"] for item in body["items"]] == [3, 1, 2]
            assert body["total"] == 3
            assert body["total_pages"] == 1

    def test_asks_the_repository_for_that_document_only(self) -> None:
        with authorized() as h:
            h.statements.list_filtered.return_value = []
            h.statements.count_by_document.return_value = 0
            h.client.get(h.url)
            assert h.statements.list_filtered.await_args.kwargs["document_id"] == (
                h.document_id
            )
            h.statements.count_by_document.assert_awaited_once_with(h.document_id)

    def test_pages_with_offset_and_limit(self) -> None:
        with authorized() as h:
            h.statements.list_filtered.return_value = []
            h.statements.count_by_document.return_value = 40
            h.client.get(h.url, params={"page": 2, "page_size": 10})
            assert h.statements.list_filtered.await_args.kwargs["offset"] == 10
            assert h.statements.list_filtered.await_args.kwargs["limit"] == 10
            assert h.client.get(h.url, params={"page": 2, "page_size": 10}).json()[
                "total_pages"
            ] == 4

    def test_empty_document_reports_zero_pages(self) -> None:
        """Not 1: there is nothing to page, and 0/0 must not be reported as 1."""
        with authorized() as h:
            h.statements.list_filtered.return_value = []
            h.statements.count_by_document.return_value = 0
            body = h.client.get(h.url).json()
            assert body["total"] == 0
            assert body["total_pages"] == 0
            assert body["items"] == []

    def test_refuses_a_document_the_caller_cannot_reach(self) -> None:
        """A 404, not an empty list.

        An empty page for another campaign's document would be
        indistinguishable from a document with no statements, which is a weaker
        contract than the document endpoints give.
        """
        with authorized(document_exists=False) as h:
            response = h.client.get(h.url)
            assert response.status_code == 404
            h.statements.list_filtered.assert_not_awaited()

    @pytest.mark.parametrize(
        "params",
        [{"page": 0}, {"page_size": 0}, {"page_size": 101}],
    )
    def test_rejects_out_of_range_paging(self, params: dict[str, int]) -> None:
        with authorized() as h:
            assert h.client.get(h.url, params=params).status_code == 422


class TestGet:
    """GET /documents/{id}/statements/{statement_id}."""

    def test_returns_the_statement(self) -> None:
        with authorized() as h:
            row = make_statement(h.document_id)
            h.statements.get.return_value = row
            response = h.client.get(f"{h.url}/{row.id}")
            assert response.status_code == 200
            assert response.json()["id"] == str(row.id)

    def test_returns_404_for_a_missing_statement(self) -> None:
        with authorized() as h:
            h.statements.get.return_value = None
            response = h.client.get(f"{h.url}/{uuid4()}")
            assert response.status_code == 404
            assert response.json()["detail"] == "Statement not found"

    def test_returns_404_for_a_statement_under_another_document(self) -> None:
        """The two ids in the path must address one resource.

        The statement is live and in the caller's campaign, so a repository-only
        check would return it — the mismatch is invisible unless the document id
        is compared too.
        """
        with authorized() as h:
            h.statements.get.return_value = make_statement(uuid4())
            response = h.client.get(f"{h.url}/{uuid4()}")
            assert response.status_code == 404
            assert response.json()["detail"] == "Statement not found"

    def test_returns_404_for_a_document_the_caller_cannot_reach(self) -> None:
        with authorized(document_exists=False) as h:
            assert h.client.get(f"{h.url}/{uuid4()}").status_code == 404
            h.statements.get.assert_not_awaited()


class TestUpdate:
    """PATCH /documents/{id}/statements/{statement_id}."""

    def test_updates_position_and_content(self) -> None:
        with authorized() as h:
            row = make_statement(h.document_id)
            h.statements.get.return_value = row
            response = h.client.patch(
                f"{h.url}/{row.id}",
                json={"position": 7, "content": "The ford is impassable."},
            )
            assert response.status_code == 200
            assert row.position == 7
            assert row.content == "The ford is impassable."

    def test_leaves_unset_fields_alone(self) -> None:
        """A partial update must not blank the field it did not mention."""
        with authorized() as h:
            row = make_statement(h.document_id, content="Original text.")
            h.statements.get.return_value = row
            h.client.patch(f"{h.url}/{row.id}", json={"position": 2})
            assert row.content == "Original text."
            assert row.position == 2

    def test_refuses_blank_content(self) -> None:
        """An empty anchor makes the facts citing it unverifiable."""
        with authorized() as h:
            row = make_statement(h.document_id)
            h.statements.get.return_value = row
            response = h.client.patch(f"{h.url}/{row.id}", json={"content": "   "})
            assert response.status_code == 422
            assert row.content == "The road forks at Kettle Ford."

    def test_refuses_an_empty_content(self) -> None:
        with authorized() as h:
            row = make_statement(h.document_id)
            h.statements.get.return_value = row
            response = h.client.patch(f"{h.url}/{row.id}", json={"content": ""})
            assert response.status_code == 422
            assert row.content == "The road forks at Kettle Ford."

    def test_patching_only_the_position_still_succeeds(self) -> None:
        """The content rule must not fire when content is not being sent.

        A use case that validated the whole model instead of the fields it is
        about to write would reject a reorder whenever the *stored* text
        happened to be blank, which is exactly the sort of surprise a
        provenance endpoint should not have.
        """
        with authorized() as h:
            row = make_statement(h.document_id, content="   ")
            h.statements.get.return_value = row
            response = h.client.patch(f"{h.url}/{row.id}", json={"position": 4})
            assert response.status_code == 200
            assert row.position == 4

    def test_rejects_moving_the_statement_to_another_document(self) -> None:
        """Provenance is the point; a statement cannot change its source."""
        with authorized() as h:
            h.statements.get.return_value = make_statement(h.document_id)
            response = h.client.patch(
                f"{h.url}/{uuid4()}", json={"document_id": str(uuid4())}
            )
            assert response.status_code == 422

    def test_returns_404_for_a_statement_under_another_document(self) -> None:
        with authorized() as h:
            h.statements.get.return_value = make_statement(uuid4())
            response = h.client.patch(f"{h.url}/{uuid4()}", json={"position": 1})
            assert response.status_code == 404

    def test_returns_404_for_a_document_the_caller_cannot_reach(self) -> None:
        with authorized(document_exists=False) as h:
            assert (
                h.client.patch(f"{h.url}/{uuid4()}", json={"position": 1}).status_code
                == 404
            )
            h.statements.get.assert_not_awaited()

    def test_rejects_unknown_fields(self) -> None:
        with authorized() as h:
            h.statements.get.return_value = make_statement(h.document_id)
            response = h.client.patch(f"{h.url}/{uuid4()}", json={"contnet": "x"})
            assert response.status_code == 422


class TestDelete:
    """DELETE /documents/{id}/statements/{statement_id}."""

    def test_returns_204_and_stamps_the_row(self) -> None:
        with authorized() as h:
            row = make_statement(h.document_id)
            h.statements.get.return_value = row
            h.statements.soft_delete.return_value = True
            response = h.client.delete(f"{h.url}/{row.id}")
            assert response.status_code == 204
            h.statements.soft_delete.assert_awaited_once_with(row.id)

    def test_returns_404_for_a_missing_statement(self) -> None:
        with authorized() as h:
            h.statements.get.return_value = None
            response = h.client.delete(f"{h.url}/{uuid4()}")
            assert response.status_code == 404
            h.statements.soft_delete.assert_not_awaited()

    def test_returns_404_for_a_statement_under_another_document(self) -> None:
        with authorized() as h:
            h.statements.get.return_value = make_statement(uuid4())
            assert h.client.delete(f"{h.url}/{uuid4()}").status_code == 404
            h.statements.soft_delete.assert_not_awaited()

    def test_returns_404_for_a_document_the_caller_cannot_reach(self) -> None:
        with authorized(document_exists=False) as h:
            assert h.client.delete(f"{h.url}/{uuid4()}").status_code == 404
            h.statements.soft_delete.assert_not_awaited()


class TestErrorTranslation:
    """Application errors map to their HTTP status."""

    def test_validation_error_maps_to_422(self) -> None:
        with authorized() as h:
            h.statements.create.side_effect = ValidationError("bad")
            assert h.client.post(h.url, json=BODY).status_code == 422
