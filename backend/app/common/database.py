"""Database helpers shared by every module.

* :func:`resolve_session` — service functions take an optional ``session`` so tests can
  pass their own; this is the one place that decides which session to use.
* :class:`UTCDateTime` — the column type for timestamps that must stay UTC (ADR-0009).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Session
from sqlalchemy.types import TypeDecorator

from app.extensions import db


def resolve_session(session: Session | None) -> Session:
    """Return the explicit session if given, else the app-bound ``db.session``."""
    return session if session is not None else db.session


class UTCDateTime(TypeDecorator[datetime]):
    """A ``timestamptz`` column that always stores and returns UTC (ADR-0009).

    Postgres keeps a timestamp's offset; SQLite, the test database, drops it. Converting
    on the way in and attaching UTC on the way out makes both behave the same, so a test
    comparing a stored time with an aware one sees what production sees.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Convert to UTC before storing. A naive value is a bug upstream: refuse it."""
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime needs a timezone-aware datetime; use as_utc() first.")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Return UTC, attaching it where the database dropped the timezone."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
