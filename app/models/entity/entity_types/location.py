"""Location entity type."""

from uuid import UUID

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Location(TimestampMixin, Base):
    """Stable canonical information for a location."""

    __tablename__ = "locations"

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True
    )
    environment: Mapped[str | None] = mapped_column(Text)
    atmosphere: Mapped[str | None] = mapped_column(Text)