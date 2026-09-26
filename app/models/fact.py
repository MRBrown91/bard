"""Fact models for campaign knowledge."""

from uuid import UUID

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EntityFact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Atomic claim about one entity."""

    __tablename__ = "entity_facts"

    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False
    )
    statement_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("document_statements.id")
    )
    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id")
    )
    fact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")

    __table_args__ = (
        Index("ix_entity_facts_campaign_entity", "campaign_id", "entity_id"),
        Index("ix_entity_facts_statement_id", "statement_id"),
        Index("ix_entity_facts_event_id", "event_id"),
    )


class EntityRelationshipFact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Atomic relationship claim between two entities."""

    __tablename__ = "entity_relationship_facts"

    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False
    )
    statement_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("document_statements.id")
    )
    source_entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    target_entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id")
    )
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")

    __table_args__ = (
        Index(
            "ix_relationship_facts_campaign_source",
            "campaign_id",
            "source_entity_id",
        ),
        Index(
            "ix_relationship_facts_campaign_target",
            "campaign_id",
            "target_entity_id",
        ),
        Index("ix_relationship_facts_statement_id", "statement_id"),
        Index("ix_relationship_facts_event_id", "event_id"),
    )