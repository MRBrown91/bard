"""Tests for the authentication and campaign-scope FastAPI dependencies."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_campaign,
    get_current_identity,
    get_current_user,
)
from app.application.campaigns.get_current_campaign import (
    get_current_campaign as get_campaign_usecase,
)
from app.application.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.integrations.auth import AuthenticatedIdentity
from app.integrations.auth.provider import StubAuthProvider
from app.models import Campaign, User
from app.repositories import CampaignRepository, UserRepository


def _identity(subject: str = "test-subject") -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        subject=subject,
        provider="stub",
        email="test@example.com",
        name="Test User",
    )


class TestGetCurrentIdentity:
    """Tests for get_current_identity dependency."""

    @pytest.mark.asyncio
    async def test_missing_authorization_header(self) -> None:
        """Missing authorization header raises UnauthorizedError."""
        with pytest.raises(UnauthorizedError) as exc_info:
            await get_current_identity(None)
        assert "Invalid authentication" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_invalid_authorization_format(self) -> None:
        """Invalid authorization format raises UnauthorizedError."""
        with pytest.raises(UnauthorizedError):
            await get_current_identity("InvalidFormat token")

    @pytest.mark.asyncio
    async def test_valid_bearer_token(self, monkeypatch) -> None:
        """Valid bearer token returns authenticated identity."""
        monkeypatch.setattr(
            "app.api.dependencies.get_auth_provider", lambda: StubAuthProvider()
        )

        identity = await get_current_identity("Bearer test-token")

        assert isinstance(identity, AuthenticatedIdentity)
        assert identity.subject == "test-user"


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_resolves_existing_user(self, monkeypatch) -> None:
        """Identity is resolved to the local user row."""
        user = User(
            id=uuid4(),
            auth_provider="stub",
            auth_subject="test-subject",
            display_name="Test User",
        )
        repo = AsyncMock(spec=UserRepository)
        repo.get_by_auth.return_value = user
        monkeypatch.setattr(
            "app.api.dependencies.UserRepository", MagicMock(return_value=repo)
        )

        result = await get_current_user(_identity(), AsyncMock(spec=AsyncSession))

        assert result is user
        repo.get_by_auth.assert_awaited_once_with("stub", "test-subject")

    @pytest.mark.asyncio
    async def test_unknown_identity_provisions_user(self, monkeypatch) -> None:
        """An unseen identity is provisioned on first authenticated request."""
        repo = AsyncMock(spec=UserRepository)
        repo.get_by_auth.return_value = None
        repo.session = AsyncMock(spec=AsyncSession)
        monkeypatch.setattr(
            "app.api.dependencies.UserRepository", MagicMock(return_value=repo)
        )

        user = await get_current_user(_identity(), AsyncMock(spec=AsyncSession))

        assert user.auth_provider == "stub"
        assert user.auth_subject == "test-subject"
        repo.session.add.assert_called_once_with(user)
        repo.session.flush.assert_awaited_once()


class TestGetCurrentCampaign:
    """Tests for the get_current_campaign dependency and its use case."""

    @pytest.mark.asyncio
    async def test_campaign_not_found_raises_404(self) -> None:
        """Non-existent campaign raises NotFoundError."""
        repo = AsyncMock(spec=CampaignRepository)
        repo.get.return_value = None

        with pytest.raises(NotFoundError):
            await get_campaign_usecase(uuid4(), uuid4(), repo)

    @pytest.mark.asyncio
    async def test_not_owner_is_indistinguishable_from_missing(self) -> None:
        """A campaign owned by someone else raises the same 404 as a missing one.

        Reporting 403 here would let any authenticated user probe campaign
        identifiers and learn which exist, so the two cases are deliberately
        identical — down to the message.
        """
        repo = AsyncMock(spec=CampaignRepository)
        repo.get.return_value = Campaign(
            id=uuid4(),
            user_id=uuid4(),
            name="Test Campaign",
        )
        campaign_id = uuid4()

        with pytest.raises(NotFoundError) as owned:
            await get_campaign_usecase(campaign_id, uuid4(), repo)

        repo.get.return_value = None
        with pytest.raises(NotFoundError) as missing:
            await get_campaign_usecase(campaign_id, uuid4(), repo)

        assert owned.value.message == missing.value.message == "Campaign not found"
        assert owned.value.details == missing.value.details

    @pytest.mark.asyncio
    async def test_owner_returns_campaign(self) -> None:
        """Owner gets the campaign."""
        campaign = Campaign(id=uuid4(), user_id=uuid4(), name="Test Campaign")
        repo = AsyncMock(spec=CampaignRepository)
        repo.get.return_value = campaign

        result = await get_campaign_usecase(campaign.id, campaign.user_id, repo)

        assert result is campaign

    @pytest.mark.asyncio
    async def test_dependency_forwards_path_campaign(
        self, monkeypatch
    ) -> None:
        """The dependency passes the path campaign id, not a query argument."""
        campaign = Campaign(id=uuid4(), user_id=uuid4(), name="Test Campaign")
        repo = AsyncMock(spec=CampaignRepository)
        repo.get.return_value = campaign
        factory = MagicMock(return_value=repo)
        monkeypatch.setattr("app.api.dependencies.CampaignRepository", factory)
        user = User(
            id=campaign.user_id,
            auth_provider="stub",
            auth_subject="test-subject",
            display_name="Test User",
        )

        result = await get_current_campaign(
            campaign.id, user, AsyncMock(spec=AsyncSession)
        )

        assert result is campaign
        repo.get.assert_awaited_once_with(campaign.id)
        factory.assert_called_once()
        assert factory.call_args[0][1] == campaign.id
