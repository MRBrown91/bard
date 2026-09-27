"""Document and statement schemas."""

from typing import Annotated
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin


class DocumentBase(BaseModel):
    """Base document fields."""

    document_type: Annotated[str, Field(min_length=1, max_length=50)]
    title: Annotated[str, Field(min_length=1, max_length=255)]
    content: str
    session_id: UUID | None = None
    source_type: Annotated[str | None, Field(default=None, max_length=50)] = None
    source_reference: Annotated[str | None, Field(default=None, max_length=500)] = None


class DocumentCreate(DocumentBase):
    """Create document request."""

    pass


class DocumentUpdate(BaseModel):
    """Update document request."""

    document_type: Annotated[str | None, Field(default=None, min_length=1, max_length=50)] = None
    title: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = None
    content: str | None = None
    session_id: UUID | None = None
    source_type: Annotated[str | None, Field(default=None, max_length=50)] = None
    source_reference: Annotated[str | None, Field(default=None, max_length=500)] = None


class DocumentRead(DocumentBase, IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin):
    """Document response."""

    model_config = ConfigDict(from_attributes=True)


class DocumentList(BaseModel):
    """Paginated document list."""

    items: list[DocumentRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class DocumentFilter(BaseModel):
    """Document filter parameters."""

    document_type: str | None = None
    session_id: UUID | None = None


class DocumentStatementBase(BaseModel):
    """Base document statement fields."""

    position: int
    content: str


class DocumentStatementCreate(DocumentStatementBase):
    """Create statement request."""

    pass


class DocumentStatementRead(DocumentStatementBase, IDMixin, TimestampMixin, SoftDeleteMixin):
    """Statement response."""

    document_id: UUID

    model_config = ConfigDict(from_attributes=True)


class DocumentWithStatementsRead(DocumentRead):
    """Document with statements loaded."""

    statements: list[DocumentStatementRead] = []