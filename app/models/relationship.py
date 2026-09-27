"""Materialized relationship model."""

from uuid import UUID

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EntityRelationship(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Materialized current relationship supported by a relationship fact."""

    __tablename__ = "entity_relationships"

    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False
    )
    source_entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    target_entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False)
    relationship_fact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("entity_relationship_facts.id"),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_relationships_campaign_source",
            "campaign_id",
            "source_entity_id",
        ),
        Index(
            "ix_relationships_campaign_target",
            "campaign_id",
            "target_entity_id",
        ),
        Index("ix_relationships_fact_id", "relationship_fact_id"),
    )