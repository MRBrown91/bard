"""User schemas."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import IDMixin, TimestampMixin, SoftDeleteMixin


class UserBase(BaseModel):
    """Base user fields."""

    auth_provider: Annotated[str, Field(min_length=1, max_length=100)]
    auth_subject: Annotated[str, Field(min_length=1, max_length=255)]
    display_name: Annotated[str, Field(min_length=1, max_length=255)]


class UserCreate(UserBase):
    """Create user request."""

    pass


class UserUpdate(BaseModel):
    """Update user request."""

    display_name: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = None


class UserRead(UserBase, IDMixin, TimestampMixin, SoftDeleteMixin):
    """User response."""

    model_config = ConfigDict(from_attributes=True)


class UserList(BaseModel):
    """Paginated user list."""

    items: list[UserRead]
    total: int
    page: int
    page_size: int
    total_pages: int