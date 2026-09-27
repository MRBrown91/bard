"""Document and statement repositories."""

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Document, DocumentStatement
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    """Repository for Document operations."""

    @property
    def model(self) -> type[Document]:
        return Document

    async def get_with_statements(self, id: UUID) -> Document | None:
        """Get document with statements loaded."""
        stmt = self._campaign_scope(
            select(Document)
            .options(selectinload(Document.statements))  # type: ignore[attr-defined]
            .where(Document.id == id)
        )
        result = await self.session.execute(stmt)
        return cast(Document | None, result.scalar_one_or_none())

    async def list_by_session(self, session_id: UUID) -> list[Document]:
        """List documents for a session."""
        stmt = self._campaign_scope(select(Document).where(Document.session_id == session_id))
        result = await self.session.execute(stmt)
        return cast(list[Document], result.scalars().all())


class DocumentStatementRepository(BaseRepository[DocumentStatement]):
    """Repository for DocumentStatement operations."""

    @property
    def model(self) -> type[DocumentStatement]:
        return DocumentStatement

    async def get_by_document(self, document_id: UUID) -> list[DocumentStatement]:
        """Get all statements for a document, ordered by position."""
        stmt = select(DocumentStatement).where(
            DocumentStatement.document_id == document_id
        ).order_by(DocumentStatement.position)
        result = await self.session.execute(stmt)
        return cast(list[DocumentStatement], result.scalars().all())