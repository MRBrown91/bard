"""Campaign, membership, and session schemas."""

from typing import Annotated
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin, PaginationParams


class CampaignBase(BaseModel):
    """Base campaign fields."""

    name: Annotated[str, Field(min_length=1, max_length=255)]
    description: str | None = None
    is_active: bool = True


class CampaignCreate(CampaignBase):
    """Create campaign request."""

    pass


class CampaignUpdate(BaseModel):
    """Update campaign request."""

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = None
    description: str | None = None
    is_active: bool | None = None


class CampaignRead(CampaignBase, IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin):
    """Campaign response."""

    user_id: UUID

    model_config = ConfigDict(from_attributes=True)


class CampaignList(BaseModel):
    """Paginated campaign list."""

    items: list[CampaignRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class CampaignMemberBase(BaseModel):
    """Base campaign member fields."""

    role: Annotated[str, Field(min_length=1, max_length=50)]


class CampaignMemberCreate(CampaignMemberBase):
    """Create campaign member request."""

    user_id: UUID


class CampaignMemberRead(CampaignMemberBase, IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin):
    """Campaign member response."""

    user_id: UUID

    model_config = ConfigDict(from_attributes=True)


class CampaignMemberList(BaseModel):
    """Campaign member list."""

    items: list[CampaignMemberRead]
    total: int


class SessionBase(BaseModel):
    """Base session fields."""

    name: Annotated[str, Field(min_length=1, max_length=255)]
    session_number: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class SessionCreate(SessionBase):
    """Create session request."""

    pass


class SessionUpdate(BaseModel):
    """Update session request."""

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = None
    session_number: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class SessionRead(SessionBase, IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin):
    """Session response."""

    model_config = ConfigDict(from_attributes=True)


class SessionList(BaseModel):
    """Paginated session list."""

    items: list[SessionRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class SessionFilter(PaginationParams):
    """Session filter parameters."""

    active_only: bool = False