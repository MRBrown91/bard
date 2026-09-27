"""Authentication provider protocol and implementations."""

from typing import Protocol

from app.integrations.auth.models import AuthenticatedIdentity, AuthenticationError


class AuthProvider(Protocol):
    """Protocol for external authentication providers."""

    async def validate_token(self, token: str) -> AuthenticatedIdentity:
        """
        Validate an OIDC access token and return the authenticated identity.

        Args:
            token: The access token to validate.

        Returns:
            AuthenticatedIdentity: The validated identity.

        Raises:
            AuthenticationError: If the token is invalid, expired, or malformed.
        """
        ...


class StubAuthProvider:
    """Authentication provider for local development and tests only.

    This provider accepts any non-empty token and returns a fixed test identity.
    It MUST NOT be used in production.
    """

    def __init__(self) -> None:
        self._test_identity = AuthenticatedIdentity(
            subject="test-user",
            provider="stub",
            email="dev@localhost",
            name="Dev User",
        )

    async def validate_token(self, token: str) -> AuthenticatedIdentity:
        """Validate token for local development.

        Args:
            token: Any non-empty string is accepted.

        Returns:
            AuthenticatedIdentity: Fixed test identity.

        Raises:
            AuthenticationError: If token is empty.
        """
        if not token or not token.strip():
            raise AuthenticationError("Token is required")
        return self._test_identity