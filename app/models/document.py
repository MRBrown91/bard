"""Document and statement models."""

from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Source document containing campaign knowledge."""

    __tablename__ = "documents"

    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False
    )
    session_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id")
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(50))
    source_reference: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        Index("ix_documents_campaign_id", "campaign_id"),
        Index("ix_documents_session_id", "session_id"),
    )


class DocumentStatement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Atomic source statement from a document."""

    __tablename__ = "document_statements"

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_document_statements_document_position", "document_id", "position"),
    )