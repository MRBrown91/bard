"""Document and statement models."""

from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentStatement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Atomic source statement from a document.

    Declared before ``Document`` because the parent's ``statements``
    relationship orders by these columns, and a relationship's ``order_by``
    only accepts real column objects, not dotted names.
    """

    __tablename__ = "document_statements"

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_document_statements_document_position", "document_id", "position"),
    )


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Source document containing campaign knowledge.

    ``content`` and ``DocumentStatement.content`` both hold text, and neither is
    derived from the other. ``content`` is the source as submitted, kept
    verbatim as provenance for the document itself; statements are the ordered
    anchors that extracted facts point at. Nothing synchronises them, so editing
    a statement never rewrites the original and vice versa.
    """

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

    # Ordering matches the explicit statement query so both read paths agree.
    # Ties on position are permitted, so created_at and id break them; without
    # them the same request could return a different order between calls.
    statements: Mapped[list[DocumentStatement]] = relationship(
        viewonly=True,
        lazy="raise_on_sql",
        order_by=(
            DocumentStatement.position,
            DocumentStatement.created_at,
            DocumentStatement.id,
        ),
        primaryjoin=(
            "and_(Document.id == DocumentStatement.document_id, "
            "DocumentStatement.deleted_at.is_(None))"
        ),
    )

    __table_args__ = (
        Index("ix_documents_campaign_id", "campaign_id"),
        Index("ix_documents_session_id", "session_id"),
    )
