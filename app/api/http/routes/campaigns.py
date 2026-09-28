"""Campaign CRUD API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    CurrentCampaign,
    CurrentUser,
    get_campaign_repo,
    get_session_repo,
)
from app.repositories import CampaignRepository, SessionRepository
from app.schemas.campaign import (
    CampaignCreate,
    CampaignList,
    CampaignRead,
    CampaignUpdate,
    SessionCreate,
    SessionList,
    SessionRead,
    SessionUpdate,
)

router = APIRouter(tags=["campaigns"])


# Campaign CRUD
@router.post(
    "/api/campaigns",
    response_model=CampaignRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_campaign(
    data: CampaignCreate,
    user: CurrentUser,
    campaign_repo: CampaignRepository = Depends(get_campaign_repo),
) -> CampaignRead:
    """Create a new campaign. Authenticated user becomes owner."""
    campaign = await campaign_repo.create(
        user_id=user.id,
        name=data.name,
        description=data.description,
        is_active=data.is_active,
    )
    return CampaignRead.model_validate(campaign)


@router.get(
    "/api/campaigns",
    response_model=CampaignList,
)
async def list_campaigns(
    user: CurrentUser,
    campaign_repo: CampaignRepository = Depends(get_campaign_repo),
    page: int = 1,
    page_size: int = 20,
) -> CampaignList:
    """List campaigns owned by the authenticated user."""
    offset = (page - 1) * page_size
    campaigns_list = await campaign_repo.list_for_user(user.id, offset=offset, limit=page_size)
    total = await campaign_repo.count_for_user(user.id)

    return CampaignList(
        items=[CampaignRead.model_validate(c) for c in campaigns_list],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get(
    "/api/campaigns/{campaign_id}",
    response_model=CampaignRead,
)
async def get_campaign(campaign: CurrentCampaign) -> CampaignRead:
    """Get campaign details. Owner only."""
    return CampaignRead.model_validate(campaign)


@router.patch(
    "/api/campaigns/{campaign_id}",
    response_model=CampaignRead,
)
async def update_campaign(
    data: CampaignUpdate,
    campaign: CurrentCampaign,
    campaign_repo: CampaignRepository = Depends(get_campaign_repo),
) -> CampaignRead:
    """Update campaign. Owner only."""
    updated = await campaign_repo.update(
        campaign.id,
        name=data.name,
        description=data.description,
        is_active=data.is_active,
    )
    return CampaignRead.model_validate(updated)


@router.delete(
    "/api/campaigns/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_campaign(
    campaign: CurrentCampaign,
    campaign_repo: CampaignRepository = Depends(get_campaign_repo),
) -> None:
    """Soft delete campaign. Owner only."""
    await campaign_repo.soft_delete(campaign.id)


# Campaign Members — Phase 2 work, deferred.
#
# These are registered but not implemented. Returning 501 is deliberate: an
# earlier version returned 201 with the campaign body, which told a client its
# member had been added when nothing was written, and the list endpoint
# returned an empty list that was indistinguishable from "this campaign has no
# members". Both lie about persistent state, so they refuse instead. The
# repository already exists (CampaignMemberRepository); wiring these up is
# Phase 2, alongside the membership-based authorization that replaces the
# owner-only check. See ADR-011.

_MEMBERS_NOT_IMPLEMENTED = "Campaign members are not implemented until Phase 2"


@router.post(
    "/api/campaigns/{campaign_id}/members",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def add_campaign_member(
    campaign_id: UUID,
    campaign: CurrentCampaign,
) -> None:
    """Not implemented. Campaign sharing arrives in Phase 2."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=_MEMBERS_NOT_IMPLEMENTED,
    )


@router.get(
    "/api/campaigns/{campaign_id}/members",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def list_campaign_members(
    campaign_id: UUID,
    campaign: CurrentCampaign,
) -> None:
    """Not implemented. Campaign sharing arrives in Phase 2."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=_MEMBERS_NOT_IMPLEMENTED,
    )


@router.delete(
    "/api/campaigns/{campaign_id}/members/{member_id}",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def remove_campaign_member(
    campaign_id: UUID,
    member_id: UUID,
    campaign: CurrentCampaign,
) -> None:
    """Not implemented. Campaign sharing arrives in Phase 2."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=_MEMBERS_NOT_IMPLEMENTED,
    )


# Sessions - nested under campaigns

@router.post(
    "/api/campaigns/{campaign_id}/sessions",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    data: SessionCreate,
    campaign: CurrentCampaign,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> SessionRead:
    """Create a new session within a campaign."""
    session = await session_repo.create(
        campaign_id=campaign.id,
        name=data.name,
        session_number=data.session_number,
        started_at=data.started_at,
        ended_at=data.ended_at,
    )
    return SessionRead.model_validate(session)


@router.get(
    "/api/campaigns/{campaign_id}/sessions",
    response_model=SessionList,
)
async def list_sessions(
    campaign: CurrentCampaign,
    session_repo: SessionRepository = Depends(get_session_repo),
    page: int = 1,
    page_size: int = 20,
    active_only: bool = False,
) -> SessionList:
    """List sessions within a campaign."""
    offset = (page - 1) * page_size

    if active_only:
        sessions = await session_repo.list_active(campaign.id, offset=offset, limit=page_size)
        total = await session_repo.count_active(campaign.id)
    else:
        sessions = await session_repo.list_by_campaign(campaign.id, offset=offset, limit=page_size)
        total = await session_repo.count_by_campaign(campaign.id)

    return SessionList(
        items=[SessionRead.model_validate(s) for s in sessions],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get(
    "/api/campaigns/{campaign_id}/sessions/{session_id}",
    response_model=SessionRead,
)
async def get_session(
    session_id: UUID,
    campaign: CurrentCampaign,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> SessionRead:
    """Get session details."""
    session = await session_repo.get(session_id)
    if not session or session.campaign_id != campaign.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return SessionRead.model_validate(session)


@router.patch(
    "/api/campaigns/{campaign_id}/sessions/{session_id}",
    response_model=SessionRead,
)
async def update_session(
    session_id: UUID,
    data: SessionUpdate,
    campaign: CurrentCampaign,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> SessionRead:
    """Update session."""
    session = await session_repo.get(session_id)
    if not session or session.campaign_id != campaign.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    updated = await session_repo.update(
        session_id,
        name=data.name,
        session_number=data.session_number,
        started_at=data.started_at,
        ended_at=data.ended_at,
    )
    return SessionRead.model_validate(updated)


@router.delete(
    "/api/campaigns/{campaign_id}/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_session(
    session_id: UUID,
    campaign: CurrentCampaign,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> None:
    """Soft delete session."""
    session = await session_repo.get(session_id)
    if not session or session.campaign_id != campaign.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    await session_repo.soft_delete(session_id)