"""Audience/visibility models for facts."""

from uuid import UUID

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EntityFactAudience(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Audience rule controlling visibility of an entity fact."""

    __tablename__ = "entity_fact_audiences"

    fact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entity_facts.id"), nullable=False
    )
    audience_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="general"
    )
    player_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("players.entity_id")
    )

    __table_args__ = (
        Index("ix_fact_audiences_fact_id", "fact_id"),
        Index("ix_fact_audiences_player_id", "player_id"),
    )


class EntityRelationshipFactAudience(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Audience rule controlling visibility of a relationship fact."""

    __tablename__ = "entity_relationship_fact_audiences"

    fact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("entity_relationship_facts.id"),
        nullable=False,
    )
    audience_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="general"
    )
    player_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("players.entity_id")
    )

    __table_args__ = (
        Index("ix_relationship_fact_audiences_fact_id", "fact_id"),
        Index("ix_relationship_fact_audiences_player_id", "player_id"),
    )