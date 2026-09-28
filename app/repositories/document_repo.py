"""Document and statement repositories."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from app.models import Document, DocumentStatement
from app.repositories.base import BaseRepository

# Deterministic statement order. Ties on position are permitted by the schema,
# so created_at and id break them; the relationship on Document orders the same
# way and the two read paths must not disagree.
STATEMENT_ORDER = (
    DocumentStatement.position,
    DocumentStatement.created_at,
    DocumentStatement.id,
)


class DocumentRepository(BaseRepository[Document]):
    """Repository for Document operations."""

    @property
    def model(self) -> type[Document]:
        return Document

    def filtered_stmt(
        self,
        document_type: str | None = None,
        session_id: UUID | None = None,
    ) -> Select[Any]:
        """Build the campaign-scoped, active, filtered document select.

        Public so the application layer can page over the identical predicate
        and count from the same subquery, which is what keeps ``total`` and
        ``len(items)`` from disagreeing.
        """
        stmt = self._active_scope(select(Document))
        stmt = self._campaign_scope(stmt)
        if document_type is not None:
            stmt = stmt.where(Document.document_type == document_type)
        if session_id is not None:
            stmt = stmt.where(Document.session_id == session_id)
        return stmt

    async def get_with_statements(self, id: UUID) -> Document | None:
        """Get an active document with its active statements loaded."""
        stmt = (
            self.filtered_stmt()
            .options(selectinload(Document.statements))
            .where(Document.id == id)
        )
        result = await self.session.execute(stmt)
        return cast(Document | None, result.scalar_one_or_none())

    async def list_filtered(
        self,
        *,
        document_type: str | None = None,
        session_id: UUID | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        """List active documents for the scoped campaign with filters.

        Ordering is ``created_at, id`` so that paging is stable: without a
        unique tiebreak, two documents created in the same transaction could
        swap places between pages.
        """
        stmt = self.filtered_stmt(document_type, session_id).order_by(
            Document.created_at, Document.id
        )
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return cast(list[Document], list(result.scalars().all()))

    async def count_filtered(
        self,
        *,
        document_type: str | None = None,
        session_id: UUID | None = None,
    ) -> int:
        """Count active documents matching the same filters as the list."""
        stmt = self.filtered_stmt(document_type, session_id)
        result = await self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        )
        return result.scalar_one()

    async def list_by_session(self, session_id: UUID) -> list[Document]:
        """List active documents for a session, in list order."""
        return await self.list_filtered(session_id=session_id)

    async def soft_delete_with_statements(self, id: UUID) -> bool:
        """Soft delete a document together with its statements.

        DATABASE.md requires that statements cannot outlive their document, and
        both rows are stamped in one transaction so a partially deleted
        document is never observable. Leaving live statements behind would not
        leak anything, because every statement read resolves the document first,
        but it is inconsistent state that a later un-delete would resurrect.
        """
        document = await self.get_with_statements(id)
        if document is None:
            return False
        now = datetime.now(UTC)
        document.deleted_at = now
        for statement in document.statements:
            statement.deleted_at = now
        await self.session.flush()
        return True


class DocumentStatementRepository(BaseRepository[DocumentStatement]):
    """Repository for DocumentStatement operations.

    ``document_statements`` has no ``campaign_id``, so the base campaign scope
    is a silent no-op here. Isolation is inherited through the parent document,
    which means every method that takes a bare ``document_id`` has to join to
    ``documents`` to establish the caller's campaign. ``_document_scope`` is
    that join, and it is used everywhere rather than relying on the base class.
    """

    @property
    def model(self) -> type[DocumentStatement]:
        return DocumentStatement

    def _document_scope(self, stmt: Select[Any]) -> Select[Any]:
        """Join the parent document and apply both scopes.

        The inner join also excludes statements whose document is soft-deleted
        or belongs to another campaign, so a statement id from elsewhere is
        simply absent rather than readable.
        """
        if self.campaign_id is None:
            return stmt
        return stmt.join(
            Document, Document.id == DocumentStatement.document_id
        ).where(Document.campaign_id == self.campaign_id)

    def filtered_stmt(self, document_id: UUID | None = None) -> Select[Any]:
        """Build the active, campaign-scoped statement select."""
        stmt = self._active_scope(select(DocumentStatement))
        stmt = self._document_scope(stmt)
        if document_id is not None:
            stmt = stmt.where(DocumentStatement.document_id == document_id)
        return stmt

    async def get_by_document(self, document_id: UUID) -> list[DocumentStatement]:
        """Get the active statements of a document, in position order."""
        stmt = self.filtered_stmt(document_id).order_by(*STATEMENT_ORDER)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_scoped(self, id: UUID) -> DocumentStatement | None:
        """Get one active statement that belongs to the scoped campaign."""
        stmt = self.filtered_stmt().where(DocumentStatement.id == id)
        result = await self.session.execute(stmt)
        return cast(DocumentStatement | None, result.scalar_one_or_none())

    async def count_by_document(self, document_id: UUID) -> int:
        """Count the active statements of a document."""
        stmt = self.filtered_stmt(document_id)
        result = await self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        )
        return result.scalar_one()

    async def list_filtered(
        self,
        *,
        document_id: UUID | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[DocumentStatement]:
        """List active statements for the scoped campaign, in position order."""
        stmt = self.filtered_stmt(document_id).order_by(*STATEMENT_ORDER)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
