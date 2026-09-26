"""Item entity type."""

from uuid import UUID

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Item(TimestampMixin, Base):
    """Stable canonical information for an item."""

    __tablename__ = "items"

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True
    )
    physical_description: Mapped[str | None] = mapped_column(Text)
    effect_description: Mapped[str | None] = mapped_column(Text)