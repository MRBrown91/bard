"""User and authentication models."""

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Authenticated application user."""

    __tablename__ = "users"

    auth_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    auth_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        Index("uq_users_auth_identity", "auth_provider", "auth_subject", unique=True),
    )