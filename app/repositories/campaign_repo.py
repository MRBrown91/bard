"""Campaign repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Campaign, CampaignMember, Session
from app.repositories.base import BaseRepository


class CampaignRepository(BaseRepository[Campaign]):
    """Repository for Campaign operations."""

    @property
    def model(self) -> type[Campaign]:
        return Campaign

    async def list_for_user(self, user_id: UUID, *, offset: int = 0, limit: int = 100) -> list[Campaign]:
        """List campaigns owned by a user."""
        stmt = select(Campaign).where(Campaign.user_id == user_id).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: UUID) -> int:
        """Count campaigns owned by a user."""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(Campaign).where(Campaign.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_with_owner(self, id: UUID) -> Campaign | None:
        """Get campaign with owner loaded."""
        stmt = select(Campaign).where(Campaign.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class CampaignMemberRepository(BaseRepository[CampaignMember]):
    """Repository for CampaignMember operations."""

    @property
    def model(self) -> type[CampaignMember]:
        return CampaignMember

    async def get_members(self, campaign_id: UUID) -> list[CampaignMember]:
        """Get all members for a campaign."""
        stmt = select(CampaignMember).where(CampaignMember.campaign_id == campaign_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def is_member(self, campaign_id: UUID, user_id: UUID) -> bool:
        """Check if user is a member of campaign."""
        stmt = select(CampaignMember).where(
            CampaignMember.campaign_id == campaign_id,
            CampaignMember.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None


class SessionRepository(BaseRepository[Session]):
    """Repository for Session operations."""

    @property
    def model(self) -> type[Session]:
        return Session

    async def get_by_number(self, campaign_id: UUID, session_number: int) -> Session | None:
        """Get session by number within campaign."""
        stmt = select(Session).where(
            Session.campaign_id == campaign_id,
            Session.session_number == session_number,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active(self, campaign_id: UUID) -> Session | None:
        """Get currently active session (no ended_at)."""
        stmt = select(Session).where(
            Session.campaign_id == campaign_id,
            Session.ended_at.is_(None),
        ).order_by(Session.started_at.desc())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_campaign(self, campaign_id: UUID, *, offset: int = 0, limit: int = 100) -> list[Session]:
        """List sessions for a campaign with pagination."""
        stmt = select(Session).where(Session.campaign_id == campaign_id).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_campaign(self, campaign_id: UUID) -> int:
        """Count sessions for a campaign."""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(Session).where(Session.campaign_id == campaign_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_active(self, campaign_id: UUID, *, offset: int = 0, limit: int = 100) -> list[Session]:
        """List active sessions for a campaign with pagination."""
        stmt = select(Session).where(
            Session.campaign_id == campaign_id,
            Session.ended_at.is_(None),
        ).offset(offset).limit(limit).order_by(Session.started_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_active(self, campaign_id: UUID) -> int:
        """Count active sessions for a campaign."""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(Session).where(
            Session.campaign_id == campaign_id,
            Session.ended_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()