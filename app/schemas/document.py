"""Document and statement schemas."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import IDMixin, TimestampMixin

# document_type and source_type are free strings. No vocabulary is defined
# anywhere in the developer docs, and naming values now would be guessing at
# product requirements. Unlike entity_type, which dispatches to one of six
# tables and therefore must be a closed set, these are labels applied to
# source material, so a new one costs nothing and is not worth blocking on.
DocumentType = Annotated[str, Field(min_length=1, max_length=50)]


class DocumentBase(BaseModel):
    """Base document fields."""

    document_type: DocumentType
    title: Annotated[str, Field(min_length=1, max_length=255)]
    content: str
    session_id: UUID | None = None
    source_type: Annotated[str | None, Field(default=None, max_length=50)] = None
    source_reference: Annotated[str | None, Field(default=None, max_length=500)] = None


class DocumentCreate(DocumentBase):
    """Create document request.

    ``extra="forbid"`` so a misspelled field is a 422 rather than a silently
    dropped value that the caller then believes was stored.
    """

    model_config = ConfigDict(extra="forbid")


class DocumentUpdate(BaseModel):
    """Update document metadata request.

    ``campaign_id`` is absent on purpose, and ``extra="forbid"`` turns an
    attempt to change it into a 422 instead of a successful no-op. Statements
    are not editable here either: they are the provenance anchors that facts
    point at, so they are managed by their own endpoints.
    """

    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType | None = None
    title: Annotated[
        str | None, Field(default=None, min_length=1, max_length=255)
    ] = None
    content: str | None = None
    session_id: UUID | None = None
    source_type: Annotated[str | None, Field(default=None, max_length=50)] = None
    source_reference: Annotated[str | None, Field(default=None, max_length=500)] = None


class DocumentRead(DocumentBase, IDMixin, TimestampMixin):
    """Document response.

    ``deleted_at`` is not exposed. Every read filters soft-deleted rows out
    (ADR-022), so a null value would be the only one a client could ever see,
    and the field would suggest a distinction the API does not make.
    """

    campaign_id: UUID

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

    model_config = ConfigDict(extra="forbid")


class DocumentStatementUpdate(BaseModel):
    """Update statement request.

    ``document_id`` is absent so a statement cannot be moved between
    documents, which would silently change the document that its facts claim
    to have come from.
    """

    model_config = ConfigDict(extra="forbid")

    position: int | None = None
    content: str | None = None


class DocumentStatementRead(DocumentStatementBase, IDMixin, TimestampMixin):
    """Statement response."""

    document_id: UUID

    model_config = ConfigDict(from_attributes=True)


class DocumentWithStatementsRead(DocumentRead):
    """Document with its active statements loaded.

    Used only by the single-document endpoint. Ordered by
    ``position, created_at, id``; ties on position are permitted, so the order
    is stable but not necessarily gapless.
    """

    statements: list[DocumentStatementRead] = Field(default_factory=list)


class DocumentStatementList(BaseModel):
    """Paginated statement list."""

    items: list[DocumentStatementRead]
    total: int
    page: int
    page_size: int
    total_pages: int
