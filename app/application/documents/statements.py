"""Document statement use cases.

Separate from ``documents.py`` because the two share no helper. Statement writes
have to prove the parent document is reachable first, which the document
use cases never do, and the document use cases need the session check that
statements have no use for.

The parent check is not redundant with the repository scope.
``document_statements`` has no ``campaign_id`` column, so
``DocumentStatementRepository.create`` has nothing to scope the insert against:
the foreign key accepts a document in any campaign. Every write here resolves
the document through ``DocumentRepository`` first, which is the same reason
``add_alias`` resolves the entity before adding an alias.
"""

from uuid import UUID

from app.application.exceptions import NotFoundError, ValidationError
from app.repositories import (
    DocumentRepository,
    DocumentStatementRepository,
)
from app.schemas.document import (
    DocumentStatementCreate,
    DocumentStatementList,
    DocumentStatementRead,
    DocumentStatementUpdate,
)


def _statement_not_found(statement_id: UUID) -> NotFoundError:
    """Build the error for a statement that is absent or out of reach.

    A statement is unreachable if it is soft-deleted, if its document is
    soft-deleted, or if it belongs to another campaign. All three produce the
    same error, for the reason given in ADR-011: distinguishing them would turn
    the endpoint into a probe for campaign contents.
    """
    return NotFoundError("Statement not found", {"statement_id": str(statement_id)})


def _document_not_found(document_id: UUID) -> NotFoundError:
    """Build the error for a document that is absent or in another campaign.

    Same reasoning as ``documents._not_found``: the repository is already scoped
    to the caller's campaign, so a miss does not distinguish the two cases.
    """
    return NotFoundError("Document not found", {"document_id": str(document_id)})


async def _require_document(
    document_id: UUID,
    document_repo: DocumentRepository,
) -> None:
    """Refuse a statement write under a document the caller cannot reach.

    Without this, a caller could name any document id and attach provenance to
    another campaign's document: the insert carries no campaign of its own, and
    the foreign key only proves the document exists. The read endpoints inherit
    isolation from the repository's join; the write path has to establish it
    itself, and this is the only place it does.
    """
    document = await document_repo.get(document_id)
    if document is None:
        raise _document_not_found(document_id)


async def create_statement(
    document_id: UUID,
    data: DocumentStatementCreate,
    document_repo: DocumentRepository,
    statement_repo: DocumentStatementRepository,
) -> DocumentStatementRead:
    """Create a statement in a document of the scoped campaign.

    ``position`` is taken as given rather than appended to, because curated
    ordering is meaningful and the schema deliberately permits duplicate
    positions (see DATABASE.md). A caller that wants a statement last sends the
    next position, and can ask the list endpoint what the current maximum is.
    """
    await _require_document(document_id, document_repo)
    statement = await statement_repo.create(
        document_id=document_id,
        position=data.position,
        content=data.content,
    )
    return DocumentStatementRead.model_validate(statement)


async def get_statement(
    document_id: UUID,
    statement_id: UUID,
    document_repo: DocumentRepository,
    statement_repo: DocumentStatementRepository,
) -> DocumentStatementRead:
    """Get one statement that is live, under a live document, in this campaign.

    ``document_id`` is in the path and therefore checked against the row, so a
    statement id from another document under the same campaign reads as a 404
    rather than as a record from somewhere else in the campaign. Otherwise the
    two ids would address two independent resources and the mismatch would be
    invisible.
    """
    await _require_document(document_id, document_repo)
    statement = await statement_repo.get(statement_id)
    if statement is None or statement.document_id != document_id:
        raise _statement_not_found(statement_id)
    return DocumentStatementRead.model_validate(statement)


async def list_statements(
    document_id: UUID,
    document_repo: DocumentRepository,
    statement_repo: DocumentStatementRepository,
    *,
    page: int = 1,
    page_size: int = 100,
) -> DocumentStatementList:
    """List a document's active statements in position order.

    The parent is resolved first so a document in another campaign is a 404
    rather than an empty list. Returning an empty page for an id the caller
    cannot see would be indistinguishable from a document with no statements,
    which is a weaker contract than the document endpoints already give.
    """
    await _require_document(document_id, document_repo)
    total = await statement_repo.count_by_document(document_id)
    items = await statement_repo.list_filtered(
        document_id=document_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return DocumentStatementList(
        items=[DocumentStatementRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )


async def update_statement(
    document_id: UUID,
    statement_id: UUID,
    data: DocumentStatementUpdate,
    document_repo: DocumentRepository,
    statement_repo: DocumentStatementRepository,
) -> DocumentStatementRead:
    """Update a statement's position or content.

    ``document_id`` cannot be changed (``DocumentStatementUpdate`` forbids it),
    so a fact that points at this statement keeps pointing at the same source
    material. Repositioning is allowed and is the point of the endpoint: the
    curated order is maintained by the caller, not by the database.
    """
    await _require_document(document_id, document_repo)
    statement = await statement_repo.get(statement_id)
    if statement is None or statement.document_id != document_id:
        raise _statement_not_found(statement_id)

    changes = data.model_dump(exclude_unset=True)
    if "content" in changes and not changes["content"].strip():
        # A blank anchor is not provenance. Facts cite a statement, and an
        # empty one makes the citation unverifiable, so this is refused at the
        # boundary rather than left for a fact to discover later.
        raise ValidationError(
            "Statement content cannot be blank", {"statement_id": str(statement_id)}
        )
    for field, value in changes.items():
        setattr(statement, field, value)

    await statement_repo.session.flush()
    await statement_repo.session.refresh(statement)
    return DocumentStatementRead.model_validate(statement)


async def delete_statement(
    document_id: UUID,
    statement_id: UUID,
    document_repo: DocumentRepository,
    statement_repo: DocumentStatementRepository,
) -> None:
    """Soft delete one statement.

    The row is retained rather than removed, for the same reason document
    deletion retains statements: facts point at them for provenance, and a
    retcon has to be able to read what a fact originally came from. The
    consequence is that provenance is retained but not readable through the
    ordinary endpoints, which filter soft-deleted rows (ADR-022). Resolving
    deleted provenance is left to the retcon tooling that will need it, which
    has to bypass ``_active_scope`` deliberately.
    """
    await _require_document(document_id, document_repo)
    statement = await statement_repo.get(statement_id)
    if statement is None or statement.document_id != document_id:
        raise _statement_not_found(statement_id)
    await statement_repo.soft_delete(statement_id)


__all__ = [
    "create_statement",
    "delete_statement",
    "get_statement",
    "list_statements",
    "update_statement",
]
