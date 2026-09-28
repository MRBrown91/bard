"""Get current campaign with owner authorization."""

from uuid import UUID

from app.models import Campaign
from app.repositories import CampaignRepository
from app.application.exceptions import NotFoundError


async def get_current_campaign(
    campaign_id: UUID,
    user_id: UUID,
    campaign_repo: CampaignRepository,
) -> Campaign:
    """Get campaign and verify ownership.

    A campaign that does not exist and a campaign owned by someone else both
    raise NotFoundError with the same message. Distinguishing them would let any
    authenticated user probe for the existence of campaign identifiers they
    cannot see, and there is nothing here to disclose: the response is the
    campaign itself, which a non-owner is never entitled to either way. This
    matches how P1B.2 resolves a wrong-type, cross-campaign, or missing entity,
    so the rule is applied the same way at both levels of the API.

    Args:
        campaign_id: The campaign ID from the request path.
        user_id: The authenticated user's ID.
        campaign_repo: Campaign repository.

    Returns:
        Campaign: The campaign if found and user owns it.

    Raises:
        NotFoundError: If the campaign does not exist or the user does not own
            it. The two cases are deliberately indistinguishable.
    """
    campaign = await campaign_repo.get(campaign_id)
    if not campaign or campaign.user_id != user_id:
        raise NotFoundError("Campaign not found", {"campaign_id": str(campaign_id)})

    return campaign
