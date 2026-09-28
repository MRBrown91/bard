"""Document use cases.

One module rather than one file per operation, because these share two
helpers: the session check on write and the not-found error on read. Splitting
them would mean importing private names across modules.
"""

from uuid import UUID

from app.application.exceptions import NotFoundError, ValidationError
from app.repositories import DocumentRepository, SessionRepository
from app.schemas.document import (
    DocumentCreate,
    DocumentList,
    DocumentRead,
    DocumentUpdate,
    DocumentWithStatementsRead,
)


def _not_found(document_id: UUID) -> NotFoundError:
    """Build the error for a document that is absent or in another campaign.

    The repository is already scoped to the caller's campaign, so a miss is
    either a document that does not exist or one belonging to someone else. The
    two are reported identically, for the reason given in ADR-011: saying which
    one it was would turn the endpoint into a probe for campaign contents.
    """
    return NotFoundError("Document not found", {"document_id": str(document_id)})


async def _validate_session(
    session_id: UUID | None,
    document_repo: DocumentRepository,
    session_repo: SessionRepository,
) -> None:
    """Reject a session that is not in the document's campaign.

    ``documents.session_id`` is a bare foreign key, so the database will accept
    a session belonging to a different campaign. That is validated here for the
    same reason ``player_characters.player_id`` is: the foreign key alone does
    not keep a link inside one campaign.

    A session that does not exist and a session owned by another campaign
    produce the same message. The caller is entitled to neither, so naming which
    one it was would only confirm that the id is real. The campaign is taken
    from ``document_repo`` rather than from the session repository, so the
    check cannot be satisfied by a repository that was never scoped.
    """
    if session_id is None:
        return
    session = await session_repo.get(session_id)
    if session is None or session.campaign_id != document_repo.campaign_id:
        raise ValidationError("Invalid session_id", {"session_id": str(session_id)})


async def create_document(
    data: DocumentCreate,
    document_repo: DocumentRepository,
    session_repo: SessionRepository,
) -> DocumentRead:
    """Create a document in the campaign the repository is scoped to.

    The campaign comes from the repository scope, which the transport layer has
    already authorized, so it cannot be supplied by the caller.
    """
    await _validate_session(data.session_id, document_repo, session_repo)
    document = await document_repo.create(
        document_type=data.document_type,
        title=data.title,
        content=data.content,
        session_id=data.session_id,
        source_type=data.source_type,
        source_reference=data.source_reference,
    )
    return DocumentRead.model_validate(document)


async def get_document(
    document_id: UUID,
    document_repo: DocumentRepository,
) -> DocumentWithStatementsRead:
    """Get one document with its active statements, ordered by position."""
    document = await document_repo.get_with_statements(document_id)
    if document is None:
        raise _not_found(document_id)
    return DocumentWithStatementsRead.model_validate(document)


async def list_documents(
    document_repo: DocumentRepository,
    *,
    document_type: str | None = None,
    session_id: UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> DocumentList:
    """List documents in the scoped campaign.

    The page and the total come from the same predicate. Counting on a
    different one is what made the specialized lists report a ``total_pages``
    that could not be reached in P1B.2.
    """
    total = await document_repo.count_filtered(
        document_type=document_type, session_id=session_id
    )
    items = await document_repo.list_filtered(
        document_type=document_type,
        session_id=session_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return DocumentList(
        items=[DocumentRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


async def update_document(
    document_id: UUID,
    data: DocumentUpdate,
    document_repo: DocumentRepository,
    session_repo: SessionRepository,
) -> DocumentWithStatementsRead:
    """Update document metadata.

    Statements come back in the response but are not modified. They are the
    anchors extracted facts point at, so editing one through this endpoint
    would move provenance without a trace; P1C.2 gives them their own endpoints.
    """
    document = await document_repo.get_with_statements(document_id)
    if document is None:
        raise _not_found(document_id)

    changes = data.model_dump(exclude_unset=True)
    if "session_id" in changes:
        await _validate_session(changes["session_id"], document_repo, session_repo)
    for field, value in changes.items():
        setattr(document, field, value)

    await document_repo.session.flush()
    await document_repo.session.refresh(document)
    return DocumentWithStatementsRead.model_validate(document)


async def delete_document(
    document_id: UUID,
    document_repo: DocumentRepository,
) -> None:
    """Soft delete a document together with its statements.

    DATABASE.md requires that statements cannot outlive their document, and both
    are stamped in one transaction. The statements are retained rather than
    removed: facts point at them for provenance, and a retcon has to be able to
    read what a fact originally came from.
    """
    if not await document_repo.soft_delete_with_statements(document_id):
        raise _not_found(document_id)


__all__ = [
    "create_document",
    "delete_document",
    "get_document",
    "list_documents",
    "update_document",
]
