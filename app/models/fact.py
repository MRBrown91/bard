"""Fact models for campaign knowledge."""

from uuid import UUID

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.audience import EntityFactAudience, EntityRelationshipFactAudience


class EntityFact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Atomic claim about one entity.

    ``content`` is the claim as stated. It is never regenerated from the
    referenced ``statement_id``; the statement is provenance, and editing one
    must not silently rewrite the other.
    """

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

    # The audience rules attached to this fact. viewonly because the writes go
    # through the audience repositories, so no backref synchronization is
    # wanted. lazy="raise_on_sql" keeps an accidental access from issuing IO
    # outside the greenlet context; the attribute is only readable when a
    # repository explicitly asked for it with selectinload. The deleted_at test
    # in primaryjoin is what stops a soft-deleted rule loading as though it were
    # live. The table has no campaign_id, so the relationship carries campaign
    # isolation only through this fact; a scoped query still has to join.
    audiences: Mapped[list[EntityFactAudience]] = relationship(
        "EntityFactAudience",
        uselist=True,
        viewonly=True,
        lazy="raise_on_sql",
        primaryjoin=(
            "and_(EntityFact.id == EntityFactAudience.fact_id, "
            "EntityFactAudience.deleted_at.is_(None))"
        ),
        order_by=lambda: (EntityFactAudience.created_at, EntityFactAudience.id),
    )

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

    # See EntityFact.audiences. Same reasoning, same shape.
    audiences: Mapped[list[EntityRelationshipFactAudience]] = relationship(
        "EntityRelationshipFactAudience",
        uselist=True,
        viewonly=True,
        lazy="raise_on_sql",
        primaryjoin=(
            "and_(EntityRelationshipFact.id == EntityRelationshipFactAudience.fact_id, "
            "EntityRelationshipFactAudience.deleted_at.is_(None))"
        ),
        order_by=lambda: (
            EntityRelationshipFactAudience.created_at,
            EntityRelationshipFactAudience.id,
        ),
    )

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
        Index("ix_relationship_facts_source_entity_id", "source_entity_id"),
        Index("ix_relationship_facts_target_entity_id", "target_entity_id"),
        Index("ix_relationship_facts_statement_id", "statement_id"),
        Index("ix_relationship_facts_event_id", "event_id"),
    )