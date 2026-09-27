"""Application-level exceptions."""

from typing import Any


class ApplicationError(Exception):
    """Base application error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(ApplicationError):
    """Resource not found."""


class UnauthorizedError(ApplicationError):
    """Authentication required or invalid."""


class ForbiddenError(ApplicationError):
    """Insufficient permissions."""


class ConflictError(ApplicationError):
    """Resource conflict."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, details)


class ValidationError(ApplicationError):
    """Application-level validation error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, details)