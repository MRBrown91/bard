"""Actor/NPC entity type."""

from uuid import UUID

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


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