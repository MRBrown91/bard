"""Tests for campaign member endpoints.

The member endpoints are registered but not implemented until Phase 2. These
tests pin that refusal, because the failure mode they replaced was worse: the
endpoints used to answer 201 with the campaign body for a write that never
happened, and 204 for a delete that never happened.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_campaign_repo, get_current_campaign
from app.main import app
from app.models import Campaign

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


@contextmanager
def authorized() -> Iterator[TestClient]:
    """Override the campaign scope so no database is needed."""

    def get_campaign() -> Campaign:
        return make_campaign()

    app.dependency_overrides[get_campaign_repo] = get_campaign
    app.dependency_overrides[get_current_campaign] = get_campaign
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


class TestMemberEndpointsAreNotImplemented:
    """The three member endpoints must refuse rather than pretend."""

    def test_add_member_returns_501(self) -> None:
        """A write that does nothing must not answer 201."""
        with authorized() as client:
            campaign_id = uuid4()
            response = client.post(
                f"/api/campaigns/{campaign_id}/members",
                json={"user_id": str(uuid4())},
            )

        assert response.status_code == 501
        assert "Phase 2" in response.json()["detail"]

    def test_list_members_returns_501(self) -> None:
        """An empty list would be indistinguishable from a campaign with no members."""
        with authorized() as client:
            response = client.get(f"/api/campaigns/{uuid4()}/members")

        assert response.status_code == 501
        assert "Phase 2" in response.json()["detail"]

    def test_remove_member_returns_501(self) -> None:
        """A delete that does nothing must not answer 204."""
        with authorized() as client:
            response = client.delete(
                f"/api/campaigns/{uuid4()}/members/{uuid4()}",
            )

        assert response.status_code == 501
        assert "Phase 2" in response.json()["detail"]

    @pytest.mark.parametrize("method", ["post", "get", "delete"])
    def test_no_endpoint_reports_success(self, method: str) -> None:
        """No member endpoint may answer 2xx while unimplemented."""
        with authorized() as client:
            url = f"/api/campaigns/{uuid4()}/members"
            if method == "post":
                response = client.post(url, json={})
            elif method == "delete":
                response = client.delete(f"{url}/{uuid4()}")
            else:
                response = client.get(url)

        assert not 200 <= response.status_code < 300
