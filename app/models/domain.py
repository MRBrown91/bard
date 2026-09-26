"""Core Dungeon Master assistant domain models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Authenticated application user."""

    __tablename__ = "users"

    auth_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    auth_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        Index("uq_users_auth_identity", "auth_provider", "auth_subject", unique=True),
    )


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
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]

    __table_args__ = (
        Index("ix_sessions_campaign_id", "campaign_id"),
        Index("uq_sessions_campaign_number", "campaign_id", "session_number", unique=True),
    )


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

    __table_args__ = (Index("ix_entity_aliases_entity_id", "entity_id"),)


class Actor(TimestampMixin, Base):
    """Stable canonical information for an actor/NPC entity."""

    __tablename__ = "actors"

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True
    )
    voice_instructions: Mapped[str | None] = mapped_column(Text)
    personality: Mapped[str | None] = mapped_column(Text)
    motivation: Mapped[str | None] = mapped_column(Text)
    appearance: Mapped[str | None] = mapped_column(Text)


class Player(TimestampMixin, Base):
    """Campaign-specific representation of a real-world player."""

    __tablename__ = "players"

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")

    __table_args__ = (Index("ix_players_user_id", "user_id"),)


class PlayerCharacter(TimestampMixin, Base):
    """Player-controlled character identity."""

    __tablename__ = "player_characters"

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True
    )
    player_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("players.entity_id"), nullable=False
    )

    __table_args__ = (Index("ix_player_characters_player_id", "player_id"),)


class Location(TimestampMixin, Base):
    """Stable canonical information for a location."""

    __tablename__ = "locations"

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True
    )
    environment: Mapped[str | None] = mapped_column(Text)
    atmosphere: Mapped[str | None] = mapped_column(Text)


class Item(TimestampMixin, Base):
    """Stable canonical information for an item."""

    __tablename__ = "items"

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True
    )
    physical_description: Mapped[str | None] = mapped_column(Text)
    effect_description: Mapped[str | None] = mapped_column(Text)


class Faction(TimestampMixin, Base):
    """Stable canonical information for a faction."""

    __tablename__ = "factions"

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True
    )
    purpose: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Source document containing campaign knowledge."""

    __tablename__ = "documents"

    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False
    )
    session_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id")
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(50))
    source_reference: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (Index("ix_documents_campaign_id", "campaign_id"),)


class DocumentStatement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Atomic source statement from a document."""

    __tablename__ = "document_statements"

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_document_statements_document_position", "document_id", "position"),
    )


class Event(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A grouping of facts describing one campaign occurrence."""

    __tablename__ = "events"

    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime | None]
    game_time: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")

    __table_args__ = (Index("ix_events_campaign_id", "campaign_id"),)


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

    __table_args__ = (Index("ix_fact_audiences_fact_id", "fact_id"),)


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

    __table_args__ = (Index("ix_relationship_fact_audiences_fact_id", "fact_id"),)
