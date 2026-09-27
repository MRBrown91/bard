"""Event schema."""

from typing import Annotated
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin


class EventBase(BaseModel):
    """Base event fields."""

    title: Annotated[str, Field(min_length=1, max_length=255)]
    description: str | None = None
    occurred_at: datetime | None = None
    game_time: Annotated[str | None, Field(default=None, max_length=255)] = None
    status: Annotated[str, Field(default="active", pattern="^(active|invalidated|superseded)$")] = "active"


class EventCreate(EventBase):
    """Create event request."""

    pass


class EventUpdate(BaseModel):
    """Update event request."""

    title: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = None
    description: str | None = None
    occurred_at: datetime | None = None
    game_time: Annotated[str | None, Field(default=None, max_length=255)] = None
    status: Annotated[str | None, Field(default=None, pattern="^(active|invalidated|superseded)$")] = None


class EventRead(EventBase, IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin):
    """Event response."""

    model_config = ConfigDict(from_attributes=True)


class EventList(BaseModel):
    """Paginated event list."""

    items: list[EventRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class EventFilter(BaseModel):
    """Event filter parameters."""

    status: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None