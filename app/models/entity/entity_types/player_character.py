"""PlayerCharacter entity type."""

from uuid import UUID

from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


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