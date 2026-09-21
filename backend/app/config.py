"""Application configuration classes.

Values are read from environment variables (loaded from a ``.env`` file by
``python-dotenv`` if present). Nothing secret is hardcoded here; the fallbacks
are development-only conveniences and must never be used in production.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import ClassVar

from dotenv import load_dotenv

load_dotenv()


def _build_database_uri() -> str:
    """Return the SQLAlchemy database URI.

    ``DATABASE_URL`` takes precedence if set. Otherwise the URI is assembled
    from the individual ``POSTGRES_*`` variables, which are the same ones the
    ``postgres`` service in ``docker-compose.yml`` consumes, so a single
    ``.env`` file configures both containers and the local backend.
    """
    explicit = os.getenv("DATABASE_URL")
    if explicit:  # pragma: no cover - environment-dependent branch (used by CI/compose)
        return explicit

    user = os.getenv("POSTGRES_USER", "connectsphere")
    password = os.getenv("POSTGRES_PASSWORD", "connectsphere")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    name = os.getenv("POSTGRES_DB", "connectsphere")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


class BaseConfig:
    """Settings shared by every environment."""

    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI: str = _build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # JWT (Flask-JWT-Extended)
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(
        seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_SECONDS", "3600"))
    )
    JWT_TOKEN_LOCATION: ClassVar[list[str]] = ["headers"]
    JWT_HEADER_NAME: str = "Authorization"
    JWT_HEADER_TYPE: str = "Bearer"
    # TODO: refresh tokens are a future story (see STORIES.md, Story 2).

    # Password policy (Story 1). Kept in config so the team can tune it
    # without touching service code.
    PASSWORD_MIN_LENGTH: int = int(os.getenv("PASSWORD_MIN_LENGTH", "8"))

    # Business timezone: decides what "today" means for date rules (ADR-0001).
    APP_TIMEZONE: str = os.getenv("APP_TIMEZONE", "Asia/Singapore")

    # Venue setup/turnaround buffer defaults (SCRUM-67). Applied whenever a
    # venue doesn't set its own value. Whether this should ever vary by
    # event type or room layout is an open question for the customer — see
    # backend/STORIES.md.
    DEFAULT_VENUE_SETUP_MINUTES: int = int(os.getenv("DEFAULT_VENUE_SETUP_MINUTES", "30"))
    DEFAULT_VENUE_TURNAROUND_MINUTES: int = int(os.getenv("DEFAULT_VENUE_TURNAROUND_MINUTES", "30"))


class DevelopmentConfig(BaseConfig):
    """Local development."""

    DEBUG: bool = True


class TestingConfig(BaseConfig):
    """Unit tests. The database is mocked, so the URI is never connected to."""

    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    # Fixed, and only ever loaded by TestingConfig — nothing it signs leaves a test.
    JWT_SECRET_KEY: str = "test-jwt-secret-must-be-at-least-32-bytes-long"  # noqa: S105
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(seconds=60)


class ProductionConfig(BaseConfig):
    """Production. Requires real secrets to be present in the environment."""

    DEBUG: bool = False


CONFIG_BY_NAME: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[BaseConfig]:
    """Resolve a config class by name, defaulting to ``FLASK_ENV`` or development."""
    key = (name or os.getenv("FLASK_ENV") or "development").lower()
    try:
        return CONFIG_BY_NAME[key]
    except KeyError as exc:  # pragma: no cover - misconfiguration guard
        raise ValueError(f"Unknown config name: {key!r}") from exc
