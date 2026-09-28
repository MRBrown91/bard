"""Document CRUD API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import (
    CurrentCampaign,
    get_document_repo,
    get_session_repo,
)
from app.application.documents.documents import (
    create_document,
    delete_document,
    get_document,
    list_documents,
    update_document,
)
from app.repositories import DocumentRepository, SessionRepository
from app.schemas.document import (
    DocumentCreate,
    DocumentList,
    DocumentRead,
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
    they cannot be created or edited here; those are P1C.2.
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
