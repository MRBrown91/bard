"""FastAPI dependencies for authentication, campaign scope, and repository injection."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.campaigns.get_current_campaign import (
    get_current_campaign as get_campaign_usecase,
)
from app.application.exceptions import UnauthorizedError
from app.application.users.resolve_current_user import resolve_current_user
from app.database.session import get_session
from app.integrations.auth import (
    AuthenticatedIdentity,
    AuthenticationError,
    get_auth_provider,
)
from app.models import Campaign, User
from app.repositories import (
    ActorRepository,
    CampaignRepository,
    DocumentRepository,
    DocumentStatementRepository,
    EntityAliasRepository,
    EntityRepository,
    EventRepository,
    FactAudienceRepository,
    FactionRepository,
    FactRepository,
    ItemRepository,
    LocationRepository,
    PlayerCharacterRepository,
    PlayerRepository,
    RelationshipFactAudienceRepository,
    RelationshipFactRepository,
    RelationshipRepository,
    SessionRepository,
    UserRepository,
)

# --- Authentication ---

async def get_current_identity(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedIdentity:
    """Extract and validate authentication token from Authorization header.

    Expected format: Authorization: Bearer <token>
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Invalid authentication credentials")

    token = authorization[7:]  # Remove "Bearer " prefix

    provider = get_auth_provider()
    try:
        return await provider.validate_token(token)
    except AuthenticationError as e:
        raise UnauthorizedError("Invalid authentication") from e


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
) -> Campaign:
    """Get campaign and verify ownership."""
    campaign_repo = CampaignRepository(session, campaign_id)
    return await get_campaign_usecase(campaign_id, user.id, campaign_repo)


# --- Campaign-Scoped Repository Factories ---

async def get_campaign_repo(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CampaignRepository:
    """Get campaign repository. Extracts campaign_id from path if present."""
    campaign_id = request.path_params.get("campaign_id")
    if campaign_id:
        campaign_id = UUID(campaign_id)
    return CampaignRepository(session, campaign_id)


async def get_session_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionRepository:
    return SessionRepository(session, campaign.id)


async def get_entity_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EntityRepository:
    return EntityRepository(session, campaign.id)


async def get_entity_alias_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EntityAliasRepository:
    return EntityAliasRepository(session, campaign.id)


async def get_document_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentRepository:
    return DocumentRepository(session, campaign.id)


async def get_document_statement_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentStatementRepository:
    return DocumentStatementRepository(session, campaign.id)


async def get_fact_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FactRepository:
    return FactRepository(session, campaign.id)


async def get_fact_audience_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FactAudienceRepository:
    return FactAudienceRepository(session, campaign.id)


async def get_relationship_fact_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RelationshipFactRepository:
    return RelationshipFactRepository(session, campaign.id)


async def get_relationship_fact_audience_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RelationshipFactAudienceRepository:
    return RelationshipFactAudienceRepository(session, campaign.id)


async def get_relationship_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RelationshipRepository:
    return RelationshipRepository(session, campaign.id)


async def get_event_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventRepository:
    return EventRepository(session, campaign.id)


async def get_actor_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ActorRepository:
    return ActorRepository(session, campaign.id)


async def get_player_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlayerRepository:
    return PlayerRepository(session, campaign.id)


async def get_player_character_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlayerCharacterRepository:
    return PlayerCharacterRepository(session, campaign.id)


async def get_location_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LocationRepository:
    return LocationRepository(session, campaign.id)


async def get_item_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ItemRepository:
    return ItemRepository(session, campaign.id)


async def get_faction_repo(
    campaign: Annotated[Campaign, Depends(get_current_campaign)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FactionRepository:
    return FactionRepository(session, campaign.id)


# --- Convenience: CurrentUser + CurrentCampaign ---

CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentCampaign = Annotated[Campaign, Depends(get_current_campaign)]
