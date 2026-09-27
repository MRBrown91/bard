"""FastAPI dependencies for authentication, campaign scope, and repository injection."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_session
from app.integrations.auth import (
    AuthenticatedIdentity,
    AuthenticationError,
    get_auth_provider,
)
from app.models import User
from app.repositories import (
    CampaignRepository,
    DocumentRepository,
    DocumentStatementRepository,
    EntityRepository,
    EntityAliasRepository,
    EventRepository,
    FactRepository,
    RelationshipFactRepository,
    RelationshipRepository,
    SessionRepository,
    UserRepository,
)
from app.application.users.resolve_current_user import resolve_current_user
from app.application.campaigns.get_current_campaign import get_current_campaign as get_campaign_usecase
from app.application.exceptions import NotFoundError, ForbiddenError, UnauthorizedError


# --- Authentication ---

async def get_current_identity(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedIdentity:
    """Extract and validate authentication token from Authorization header.

    Expected format: Authorization: Bearer <token>
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[7:]  # Remove "Bearer " prefix

    try:
        provider = get_auth_provider()
        return await provider.validate_token(token)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_current_user(
    identity: Annotated[AuthenticatedIdentity, Depends(get_current_identity)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Resolve the local User from authenticated identity."""
    user_repo = UserRepository(session, campaign_id=None)  # Users not campaign-scoped
    return await resolve_current_user(identity, user_repo)


# --- Campaign Scope ---

async def get_current_campaign(
    campaign_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> "Campaign":
    """Get campaign and verify ownership."""
    campaign_repo = CampaignRepository(session, campaign_id)
    try:
        return await get_campaign_usecase(campaign_id, user.id, campaign_repo)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message) from e


# --- Campaign-Scoped Repository Factories ---

async def get_campaign_repo(
    campaign_id: Annotated[UUID, Path()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CampaignRepository:
    return CampaignRepository(session, campaign_id)


async def get_session_repo(
    campaign: Annotated["Campaign", Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionRepository:
    return SessionRepository(session, campaign.id)


async def get_entity_repo(
    campaign: Annotated["Campaign", Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EntityRepository:
    return EntityRepository(session, campaign.id)


async def get_entity_alias_repo(
    campaign: Annotated["Campaign", Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EntityAliasRepository:
    return EntityAliasRepository(session, campaign.id)


async def get_document_repo(
    campaign: Annotated["Campaign", Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentRepository:
    return DocumentRepository(session, campaign.id)


async def get_document_statement_repo(
    campaign: Annotated["Campaign", Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentStatementRepository:
    return DocumentStatementRepository(session, campaign.id)


async def get_fact_repo(
    campaign: Annotated["Campaign", Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FactRepository:
    return FactRepository(session, campaign.id)


async def get_relationship_fact_repo(
    campaign: Annotated["Campaign", Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RelationshipFactRepository:
    return RelationshipFactRepository(session, campaign.id)


async def get_relationship_repo(
    campaign: Annotated["Campaign", Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RelationshipRepository:
    return RelationshipRepository(session, campaign.id)


async def get_event_repo(
    campaign: Annotated["Campaign", Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventRepository:
    return EventRepository(session, campaign.id)


# --- Convenience: CurrentUser + CurrentCampaign ---

CurrentUser = Annotated[User, Depends(get_current_user)]

from app.models import Campaign
CurrentCampaign = Annotated[Campaign, Depends(get_current_campaign)]