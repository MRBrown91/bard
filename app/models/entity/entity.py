"""Core entity identity models."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    # Imported for type checking only. At runtime the relationships reference
    # these by class name, which SQLAlchemy resolves against the declarative
    # registry, so this module never imports entity_types and there is no cycle.
    from app.models.entity.entity_types import (
        Actor,
        Faction,
        Item,
        Location,
        Player,
        PlayerCharacter,
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

    # One-to-one specializations. Each is keyed on entity_id, which is both the
    # primary key and the foreign key, so the join is unique. uselist=False is
    # required: without it SQLAlchemy infers a collection. The deleted_at test
    # in primaryjoin is what stops a soft-deleted specialization loading as
    # though it were live.
    #
    # lazy="raise_on_sql" turns the async footgun into an immediate error: the
    # attribute is only readable when a repository explicitly asked for it with
    # selectinload. viewonly because writes go through the specialized
    # repositories, so no backref synchronization is wanted.
    actor: Mapped["Actor | None"] = relationship(
        "Actor",
        uselist=False,
        viewonly=True,
        lazy="raise_on_sql",
        primaryjoin="and_(Entity.id == Actor.entity_id, Actor.deleted_at.is_(None))",
    )
    player: Mapped["Player | None"] = relationship(
        "Player",
        uselist=False,
        viewonly=True,
        lazy="raise_on_sql",
        primaryjoin="and_(Entity.id == Player.entity_id, Player.deleted_at.is_(None))",
    )
    player_character: Mapped["PlayerCharacter | None"] = relationship(
        "PlayerCharacter",
        uselist=False,
        viewonly=True,
        lazy="raise_on_sql",
        primaryjoin=(
            "and_(Entity.id == PlayerCharacter.entity_id, "
            "PlayerCharacter.deleted_at.is_(None))"
        ),
    )
    location: Mapped["Location | None"] = relationship(
        "Location",
        uselist=False,
        viewonly=True,
        lazy="raise_on_sql",
        primaryjoin=(
            "and_(Entity.id == Location.entity_id, "
            "Location.deleted_at.is_(None))"
        ),
    )
    item: Mapped["Item | None"] = relationship(
        "Item",
        uselist=False,
        viewonly=True,
        lazy="raise_on_sql",
        primaryjoin="and_(Entity.id == Item.entity_id, Item.deleted_at.is_(None))",
    )
    faction: Mapped["Faction | None"] = relationship(
        "Faction",
        uselist=False,
        viewonly=True,
        lazy="raise_on_sql",
        primaryjoin=(
            "and_(Entity.id == Faction.entity_id, Faction.deleted_at.is_(None))"
        ),
    )

    # Aliases. Ordering matches the explicit query so both read paths agree.
    aliases: Mapped[list["EntityAlias"]] = relationship(
        "EntityAlias",
        viewonly=True,
        lazy="raise_on_sql",
        order_by="EntityAlias.alias",
        primaryjoin=(
            "and_(Entity.id == EntityAlias.entity_id, "
            "EntityAlias.deleted_at.is_(None))"
        ),
    )

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