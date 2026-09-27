"""Resolve current user from authenticated identity."""

from app.integrations.auth import AuthenticatedIdentity
from app.models import User
from app.repositories import UserRepository


async def resolve_current_user(
    identity: AuthenticatedIdentity,
    user_repo: UserRepository,
) -> User:
    """Resolve or provision the local User for an authenticated identity.

    Args:
        identity: The authenticated external identity.
        user_repo: User repository for persistence access.

    Returns:
        User: The local Bard user.
    """
    # Try to find existing user
    user = await user_repo.get_by_auth(identity.provider, identity.subject)
    if user:
        return user

    # Provision new user
    user = User(
        auth_provider=identity.provider,
        auth_subject=identity.subject,
        display_name=identity.name or identity.email or identity.subject,
    )
    user_repo.session.add(user)
    await user_repo.session.flush()
    return user