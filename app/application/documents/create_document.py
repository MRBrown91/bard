"""Create document use case."""

from uuid import UUID

from app.application.exceptions import ValidationError
from app.repositories import DocumentRepository, SessionRepository
from app.schemas.document import DocumentCreate, DocumentRead


async def create_document(
    data: DocumentCreate,
    document_repo: DocumentRepository,
    session_repo: SessionRepository,
) -> DocumentRead:
    """Create a document in the campaign the repository is scoped to.

    The campaign is taken from the repository scope, which the transport layer
    has already authorized, so it cannot be supplied by the caller.

    ``documents.session_id`` is a bare foreign key, so the database will happily
    accept a session belonging to a different campaign. That is validated here
    for the same reason ``player_characters.player_id`` is: the FK alone does
    not guarantee the link stays inside one campaign.
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


async def _validate_session(
    session_id: UUID | None,
    document_repo: DocumentRepository,
    session_repo: SessionRepository,
) -> None:
    """Reject a session that is not in the document's campaign.

    A session that does not exist and a session owned by another campaign
    produce the same message. Saying which one it was would confirm that a
    session id is real, which is the same existence oracle ADR-011 closed for
    campaigns; the caller is not entitled to either session, so the distinction
    protects nothing.

    The scoping is taken from ``document_repo`` rather than ``session_repo`` so
    the check cannot be satisfied by a repository that was never scoped to the
    campaign being written to.
    """
    if session_id is None:
        return
    session = await session_repo.get(session_id)
    if session is None or session.campaign_id != document_repo.campaign_id:
        raise ValidationError("Invalid session_id", {"session_id": str(session_id)})
