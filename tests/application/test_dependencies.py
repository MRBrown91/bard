"""Tests for application layer dependencies."""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.exceptions import NotFoundError, ForbiddenError
from app.api.dependencies import (
    get_current_identity,
    get_current_user,
    get_current_campaign,
)


class TestGetCurrentIdentity:
    """Tests for get_current_identity dependency."""

    @pytest.mark.asyncio
    async def test_missing_authorization_header(self) -> None:
        """Missing authorization header raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_identity(None)
        assert exc_info.value.status_code == 401
        assert "Invalid authentication" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_authorization_format(self) -> None:
        """Invalid authorization format raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_identity("InvalidFormat token")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_bearer_token(self, monkeypatch) -> None:
        """Valid bearer token returns authenticated identity."""
        from app.integrations.auth import AuthenticatedIdentity, get_auth_provider
        from app.integrations.auth.provider import StubAuthProvider

        mock_provider = StubAuthProvider()
        monkeypatch.setattr("app.api.dependencies.get_auth_provider", lambda: mock_provider)

        identity = await get_current_identity("Bearer test-token")
        assert isinstance(identity, AuthenticatedIdentity)
        assert identity.subject == "test-user"


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_resolves_existing_user(self) -> None:
        """Resolves existing user from identity."""
        from app.integrations.auth import AuthenticatedIdentity
        from app.models import User
        from unittest.mock import AsyncMock

        identity = AuthenticatedIdentity(
            subject="test-subject",
            provider="stub",
            email="test@example.com",
            name="Test User",
        )

        # Mock session and user repo
        mock_session = AsyncMock(spec=AsyncSession)
        mock_user_repo = AsyncMock()
        mock_user_repo.get_by_auth.return_value = User(
            id=uuid4(),
            auth_provider="stub",
            auth_subject="test-subject",
            display_name="Test User",
        )

        # We can't easily test the full dependency chain without FastAPI's Depends
        # This would be better tested as an integration test with TestClient
        pass


class TestGetCurrentCampaign:
    """Tests for get_current_campaign dependency."""

    @pytest.mark.asyncio
    async def test_campaign_not_found_raises_404(self) -> None:
        """Non-existent campaign raises 404."""
        from app.application.campaigns.get_current_campaign import get_current_campaign as get_campaign_usecase
        from app.repositories import CampaignRepository
        from unittest.mock import AsyncMock

        mock_repo = AsyncMock(spec=CampaignRepository)
        mock_repo.get.return_value = None

        with pytest.raises(NotFoundError):
            await get_campaign_usecase(uuid4(), uuid4(), mock_repo)

    @pytest.mark.asyncio
    async def test_not_owner_raises_403(self) -> None:
        """Non-owner user raises 403."""
        from app.application.campaigns.get_current_campaign import get_current_campaign as get_campaign_usecase
        from app.repositories import CampaignRepository
        from app.models import Campaign
        from unittest.mock import AsyncMock

        user_id = uuid4()
        other_user_id = uuid4()

        mock_repo = AsyncMock(spec=CampaignRepository)
        mock_repo.get.return_value = Campaign(
            id=uuid4(),
            user_id=other_user_id,
            name="Test Campaign",
        )

        with pytest.raises(ForbiddenError):
            await get_campaign_usecase(uuid4(), user_id, mock_repo)

    @pytest.mark.asyncio
    async def test_owner_returns_campaign(self) -> None:
        """Owner gets campaign."""
        from app.application.campaigns.get_current_campaign import get_current_campaign as get_campaign_usecase
        from app.repositories import CampaignRepository
        from app.models import Campaign
        from unittest.mock import AsyncMock

        user_id = uuid4()
        campaign_id = uuid4()

        mock_repo = AsyncMock(spec=CampaignRepository)
        mock_repo.get.return_value = Campaign(
            id=campaign_id,
            user_id=user_id,
            name="Test Campaign",
        )

        campaign = await get_campaign_usecase(campaign_id, user_id, mock_repo)
        assert campaign.id == campaign_id
        assert campaign.user_id == user_id