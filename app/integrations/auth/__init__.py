"""Authentication provider factory and exports."""

from typing import TYPE_CHECKING

from app.core.config import settings
from app.integrations.auth.models import AuthenticatedIdentity, AuthenticationError
from app.integrations.auth.provider import AuthProvider, StubAuthProvider

if TYPE_CHECKING:
    from app.core.config import Settings


def get_auth_provider(*, settings_override: "Settings | None" = None) -> AuthProvider:
    """Return the configured authentication provider.

    Args:
        settings_override: Optional settings for testing. Uses global settings if not provided.

    Returns:
        AuthProvider: The configured provider instance.

    Raises:
        ValueError: If the configured provider is unsupported or stub is used in production.
    """
    cfg = settings_override or settings

    if cfg.oidc_provider == "stub":
        # Prevent stub provider in production
        if cfg.app_env == "production":
            raise ValueError(
                "Stub authentication provider cannot be used in production. "
                "Configure a real OIDC provider."
            )
        return StubAuthProvider()

    raise ValueError(
        f"Unsupported authentication provider: {cfg.oidc_provider}. "
        f"Supported: 'stub'"
    )


__all__ = [
    "AuthProvider",
    "StubAuthProvider",
    "AuthenticatedIdentity",
    "AuthenticationError",
    "get_auth_provider",
]