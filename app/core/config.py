"""Application configuration."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://bard:bard@localhost:5433/bard"
    oidc_provider: Literal["stub"] = "stub"
    oidc_issuer_url: str | None = None
    oidc_audience: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()