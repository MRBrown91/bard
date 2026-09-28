"""Campaign, membership, and session models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Campaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A campaign owned by an application user."""

    __tablename__ = "campaigns"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship()

    __table_args__ = (Index("ix_campaigns_user_id", "user_id"),)


class CampaignMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Future sharing membership for a campaign."""

    __tablename__ = "campaign_members"

    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        Index(
            "uq_campaign_members_campaign_user",
            "campaign_id",
            "user_id",
            unique=True,
        ),
    )


class Session(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An actual D&D play session within a campaign."""

    __tablename__ = "sessions"

    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    session_number: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_sessions_campaign_id", "campaign_id"),
        Index(
            "uq_sessions_campaign_number",
            "campaign_id",
            "session_number",
            unique=True,
        ),
    )