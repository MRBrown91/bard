"""Get current campaign with owner authorization."""

from uuid import UUID

from app.models import Campaign
from app.repositories import CampaignRepository
from app.application.exceptions import NotFoundError, ForbiddenError


async def get_current_campaign(
    campaign_id: UUID,
    user_id: UUID,
    campaign_repo: CampaignRepository,
) -> Campaign:
    """Get campaign and verify ownership.

    Args:
        campaign_id: The campaign ID from the request path.
        user_id: The authenticated user's ID.
        campaign_repo: Campaign repository.

    Returns:
        Campaign: The campaign if found and user owns it.

    Raises:
        NotFoundError: If campaign doesn't exist.
        ForbiddenError: If user doesn't own the campaign.
    """
    campaign = await campaign_repo.get(campaign_id)
    if not campaign:
        raise NotFoundError("Campaign not found", {"campaign_id": str(campaign_id)})

    if campaign.user_id != user_id:
        raise ForbiddenError(
            "Not campaign owner",
            {"campaign_id": str(campaign_id), "user_id": str(user_id)},
        )

    return campaign