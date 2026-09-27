"""Authentication data models."""

from pydantic import BaseModel, ConfigDict


class AuthenticatedIdentity(BaseModel):
    """Identity established by successful external authentication."""

    subject: str
    provider: str
    email: str | None = None
    name: str | None = None

    model_config = ConfigDict(frozen=True)


class AuthenticationError(Exception):
    """Provider-independent authentication error."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)
        self.message = message