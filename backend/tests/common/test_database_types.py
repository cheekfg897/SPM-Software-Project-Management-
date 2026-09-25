"""Unit tests for :class:`app.common.database.UTCDateTime` (SCRUM-26, ADR-0009).

The column type makes SQLite, which drops timezones, behave like Postgres: what goes in
is UTC, and what comes out is always timezone-aware UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.dialects import sqlite

from app.common.database import UTCDateTime

pytestmark = pytest.mark.scrum_26

DIALECT = sqlite.dialect()
SINGAPORE = ZoneInfo("Asia/Singapore")
NINE_AM_SINGAPORE = datetime(2026, 10, 1, 9, 0, tzinfo=SINGAPORE)
ONE_AM_UTC = datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)
#: Naive values, as SQLite returns them or as a buggy caller might pass them.
NINE_AM_NO_OFFSET = datetime(2026, 10, 1, 9, 0)  # noqa: DTZ001
ONE_AM_NO_OFFSET = datetime(2026, 10, 1, 1, 0)  # noqa: DTZ001


def test_an_aware_time_is_stored_as_utc() -> None:
    stored = UTCDateTime().process_bind_param(NINE_AM_SINGAPORE, DIALECT)

    assert stored == ONE_AM_UTC
    assert stored.tzinfo is timezone.utc


def test_a_naive_time_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match="timezone"):
        UTCDateTime().process_bind_param(NINE_AM_NO_OFFSET, DIALECT)


def test_a_naive_value_read_back_is_utc() -> None:
    """SQLite returns the stored UTC wall-clock time with no timezone attached."""
    loaded = UTCDateTime().process_result_value(ONE_AM_NO_OFFSET, DIALECT)

    assert loaded == ONE_AM_UTC
    assert loaded.tzinfo is timezone.utc


def test_an_aware_value_read_back_is_converted_to_utc() -> None:
    loaded = UTCDateTime().process_result_value(NINE_AM_SINGAPORE, DIALECT)

    assert loaded == ONE_AM_UTC
    assert loaded.tzinfo is timezone.utc


@pytest.mark.parametrize("method", ["process_bind_param", "process_result_value"])
def test_null_passes_through(method: str) -> None:
    assert getattr(UTCDateTime(), method)(None, DIALECT) is None
