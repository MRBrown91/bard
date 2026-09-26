"""Core entity identity models."""

from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Entity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable identity for a campaign entity."""

    __tablename__ = "entities"

    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_entities_campaign_id", "campaign_id"),
        Index("ix_entities_campaign_name", "campaign_id", "name"),
    )


class EntityAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Alternative name used to identify an entity."""

    __tablename__ = "entity_aliases"

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        Index("ix_entity_aliases_entity_id", "entity_id"),
        Index("uq_entity_aliases_entity_alias", "entity_id", "alias", unique=True),
    )