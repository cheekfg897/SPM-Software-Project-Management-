"""Application clock — the one place "today" is worked out.

ConnectSphere runs its calendar in a single business timezone (ADR-0001),
configured by ``APP_TIMEZONE`` and defaulting to ``Asia/Singapore``. The
server itself may run in UTC, so never call ``date.today()`` for business
rules; use :func:`local_today` instead.

Validation code should take "today" as an argument where it can, so tests can
pin the date instead of depending on when they run.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from flask import current_app, has_app_context

DEFAULT_APP_TIMEZONE = "Asia/Singapore"


def app_timezone() -> ZoneInfo:
    """Return the configured business timezone."""
    if has_app_context():
        return ZoneInfo(current_app.config.get("APP_TIMEZONE", DEFAULT_APP_TIMEZONE))
    return ZoneInfo(DEFAULT_APP_TIMEZONE)  # pragma: no cover - only hit outside an app context


def local_today(now: datetime | None = None) -> date:
    """Return today's date in the business timezone.

    Args:
        now: A timezone-aware instant to convert (for tests). Defaults to the
            current time.

    Raises:
        ValueError: if ``now`` is naive, since its timezone would be a guess.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        raise ValueError("local_today() needs a timezone-aware datetime")
    return now.astimezone(app_timezone()).date()
