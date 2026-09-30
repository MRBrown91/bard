"""Document CRUD API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import (
    CurrentCampaign,
    get_document_repo,
    get_document_statement_repo,
    get_session_repo,
)
from app.application.documents.documents import (
    create_document,
    delete_document,
    get_document,
    list_documents,
    update_document,
)
from app.application.documents.statements import (
    create_statement,
    delete_statement,
    get_statement,
    list_statements,
    update_statement,
)
from app.repositories import (
    DocumentRepository,
    DocumentStatementRepository,
    SessionRepository,
)
from app.schemas.document import (
    DocumentCreate,
    DocumentList,
    DocumentRead,
    DocumentStatementCreate,
    DocumentStatementList,
    DocumentStatementRead,
    DocumentStatementUpdate,
    DocumentUpdate,
    DocumentWithStatementsRead,
)

router = APIRouter(prefix="/api/campaigns", tags=["documents"])


@router.post(
    "/{campaign_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_document_endpoint(
    data: DocumentCreate,
    campaign: CurrentCampaign,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    session_repo: Annotated[SessionRepository, Depends(get_session_repo)],
) -> DocumentRead:
    """Create a document in the campaign.

    ``session_id`` is optional; omitting it marks the document as campaign-level
    source material rather than something tied to a play session.
    """
    return await create_document(data, document_repo, session_repo)


@router.get("/{campaign_id}/documents", response_model=DocumentList)
async def list_documents_endpoint(
    campaign: CurrentCampaign,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    document_type: Annotated[str | None, Query(max_length=50)] = None,
    session_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DocumentList:
    """List documents with optional type and session filters."""
    return await list_documents(
        document_repo,
        document_type=document_type,
        session_id=session_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{campaign_id}/documents/{document_id}",
    response_model=DocumentWithStatementsRead,
)
async def get_document_endpoint(
    campaign_id: UUID,
    document_id: UUID,
    campaign: CurrentCampaign,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repo)],
) -> DocumentWithStatementsRead:
    """Get one document with its statements.

    Statements are included here because they are part of the document, but
    they cannot be created or edited here; those have their own nested
    endpoints.
    """
    return await get_document(document_id, document_repo)


@router.patch(
    "/{campaign_id}/documents/{document_id}",
    response_model=DocumentWithStatementsRead,
)
async def update_document_endpoint(
    campaign_id: UUID,
    document_id: UUID,
    data: DocumentUpdate,
    campaign: CurrentCampaign,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    session_repo: Annotated[SessionRepository, Depends(get_session_repo)],
) -> DocumentWithStatementsRead:
    """Update document metadata, leaving statements untouched."""
    return await update_document(document_id, data, document_repo, session_repo)


@router.delete(
    "/{campaign_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document_endpoint(
    campaign_id: UUID,
    document_id: UUID,
    campaign: CurrentCampaign,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repo)],
) -> None:
    """Soft delete a document and its statements.

    A 204 means the rows are no longer readable, not that they are gone. They
    are retained so facts extracted from them keep resolvable provenance and a
    retcon can be reversed.
    """
    await delete_document(document_id, document_repo)


# Statements are nested under their document rather than exposed at campaign
# level, because that is the only place their campaign is knowable:
# document_statements carries no campaign_id and inherits isolation through its
# parent (DATABASE.md). The document id in every path is what establishes it.
_STATEMENT_REPOS = Annotated[
    DocumentStatementRepository, Depends(get_document_statement_repo)
]


@router.post(
    "/{campaign_id}/documents/{document_id}/statements",
    response_model=DocumentStatementRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_statement_endpoint(
    campaign_id: UUID,
    document_id: UUID,
    data: DocumentStatementCreate,
    campaign: CurrentCampaign,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    statement_repo: _STATEMENT_REPOS,
) -> DocumentStatementRead:
    """Create a statement in a document of this campaign.

    ``position`` is caller-supplied and is not checked for uniqueness, because
    the schema permits ties and resolves them by ``created_at, id``.
    """
    return await create_statement(document_id, data, document_repo, statement_repo)


@router.get(
    "/{campaign_id}/documents/{document_id}/statements",
    response_model=DocumentStatementList,
)
async def list_statements_endpoint(
    campaign_id: UUID,
    document_id: UUID,
    campaign: CurrentCampaign,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    statement_repo: _STATEMENT_REPOS,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 100,
) -> DocumentStatementList:
    """List a document's statements in position order."""
    return await list_statements(
        document_id, document_repo, statement_repo, page=page, page_size=page_size
    )


@router.get(
    "/{campaign_id}/documents/{document_id}/statements/{statement_id}",
    response_model=DocumentStatementRead,
)
async def get_statement_endpoint(
    campaign_id: UUID,
    document_id: UUID,
    statement_id: UUID,
    campaign: CurrentCampaign,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    statement_repo: _STATEMENT_REPOS,
) -> DocumentStatementRead:
    """Get one statement by id.

    The statement must belong to the document named in the path; a mismatch is
    a 404, not a record from another part of the campaign.
    """
    return await get_statement(
        document_id, statement_id, document_repo, statement_repo
    )


@router.patch(
    "/{campaign_id}/documents/{document_id}/statements/{statement_id}",
    response_model=DocumentStatementRead,
)
async def update_statement_endpoint(
    campaign_id: UUID,
    document_id: UUID,
    statement_id: UUID,
    data: DocumentStatementUpdate,
    campaign: CurrentCampaign,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    statement_repo: _STATEMENT_REPOS,
) -> DocumentStatementRead:
    """Update a statement's position or content.

    The document cannot be changed here, so a fact citing this statement keeps
    citing the same source material.
    """
    return await update_statement(
        document_id, statement_id, data, document_repo, statement_repo
    )


@router.delete(
    "/{campaign_id}/documents/{document_id}/statements/{statement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_statement_endpoint(
    campaign_id: UUID,
    document_id: UUID,
    statement_id: UUID,
    campaign: CurrentCampaign,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repo)],
    statement_repo: _STATEMENT_REPOS,
) -> None:
    """Soft delete one statement.

    The row is retained for provenance and is no longer returned by any read
    here. See the use case for what that implies for retcon tooling.
    """
    await delete_statement(document_id, statement_id, document_repo, statement_repo)
