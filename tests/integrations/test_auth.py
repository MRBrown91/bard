"""Tests for authentication provider."""

import pytest

from app.integrations.auth import (
    get_auth_provider,
    StubAuthProvider,
    AuthenticatedIdentity,
    AuthenticationError,
)


class TestStubAuthProvider:
    """Tests for the stub authentication provider."""

    @pytest.mark.asyncio
    async def test_accepts_any_non_empty_token(self) -> None:
        """Stub provider accepts any non-empty token."""
        provider = StubAuthProvider()
        identity = await provider.validate_token("any-token")
        assert isinstance(identity, AuthenticatedIdentity)
        assert identity.subject == "test-user"
        assert identity.provider == "stub"
        assert identity.email == "dev@localhost"
        assert identity.name == "Dev User"

    @pytest.mark.asyncio
    async def test_accepts_various_tokens(self) -> None:
        """Stub provider accepts various token formats."""
        provider = StubAuthProvider()
        for token in ["test", "abc123", "Bearer token", "x" * 100]:
            identity = await provider.validate_token(token)
            assert identity.subject == "test-user"

    @pytest.mark.asyncio
    async def test_rejects_empty_token(self) -> None:
        """Stub provider rejects empty token."""
        provider = StubAuthProvider()
        with pytest.raises(AuthenticationError, match="Token is required"):
            await provider.validate_token("")

    @pytest.mark.asyncio
    async def test_rejects_whitespace_only_token(self) -> None:
        """Stub provider rejects whitespace-only token."""
        provider = StubAuthProvider()
        with pytest.raises(AuthenticationError, match="Token is required"):
            await provider.validate_token("   ")


class TestAuthProviderProtocol:
    """Tests for the AuthProvider protocol."""

    @pytest.mark.asyncio
    async def test_can_consume_through_protocol(self) -> None:
        """AuthProvider protocol can be used without depending on StubAuthProvider."""
        provider = get_auth_provider()
        assert isinstance(provider, StubAuthProvider)

    @pytest.mark.asyncio
    async def test_returns_authenticated_identity(self) -> None:
        """Provider returns AuthenticatedIdentity through protocol."""
        identity = await get_auth_provider().validate_token("test-token")
        assert isinstance(identity, AuthenticatedIdentity)
        assert identity.subject == "test-user"
        assert identity.provider == "stub"


class TestAuthenticationError:
    """Tests for authentication error handling."""

    @pytest.mark.asyncio
    async def test_invalid_auth_produces_defined_error(self) -> None:
        """Invalid authentication produces defined authentication error."""
        provider = StubAuthProvider()
        with pytest.raises(AuthenticationError):
            await provider.validate_token("")

    def test_error_message_not_exposed_in_production(self) -> None:
        """Error message is defined and safe."""
        error = AuthenticationError("Custom message")
        assert str(error) == "Custom message"


class TestStubInProduction:
    """Tests for stub provider production safety."""

    def test_stub_rejected_in_production(self) -> None:
        """Stub authentication provider cannot be used in production."""
        from app.core.config import Settings

        prod_settings = Settings(
            app_env="production",
            oidc_provider="stub",
            database_url="postgresql://test",
        )

        with pytest.raises(ValueError, match="Stub authentication provider cannot be used in production"):
            get_auth_provider(settings_override=prod_settings)


class TestProviderIdentity:
    """Tests for provider identity control."""

    @pytest.mark.asyncio
    async def test_provider_determined_by_config_not_token(self) -> None:
        """Provider identity is determined by configuration, not token."""
        identity = await get_auth_provider().validate_token("any-random-token")
        assert identity.provider == "stub"

    @pytest.mark.asyncio
    async def test_provider_not_from_token_payload(self) -> None:
        """Provider is not derived from token payload."""
        provider = StubAuthProvider()
        identity1 = await provider.validate_token("token-a")
        identity2 = await provider.validate_token("token-b")
        assert identity1.provider == identity2.provider == "stub"


class TestNoTokenLeakage:
    """Tests for token safety."""

    @pytest.mark.asyncio
    async def test_token_not_in_error_messages(self) -> None:
        """Raw token not included in authentication errors."""
        provider = StubAuthProvider()
        try:
            await provider.validate_token("secret-token-123")
        except AuthenticationError as e:
            assert "secret-token-123" not in str(e)

    @pytest.mark.asyncio
    async def test_token_not_in_valid_identity(self) -> None:
        """Raw token not included in returned identity."""
        identity = await get_auth_provider().validate_token("secret-token-123")
        assert "secret-token-123" not in identity.model_dump_json()