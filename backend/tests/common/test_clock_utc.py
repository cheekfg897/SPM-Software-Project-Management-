"""Unit tests for the UTC and business-time helpers in ``app.common.clock`` (ADR-0009).

Booking and block times are stored and compared in UTC. A time sent without an offset
is read as business time (``APP_TIMEZONE``), the same rule event requests follow, and
responses show times in business time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from flask import Flask

from app.common.clock import as_utc, to_business_time

pytestmark = pytest.mark.scrum_26

SINGAPORE = ZoneInfo("Asia/Singapore")
#: A time sent with no offset: the naive input these tests are about.
NINE_AM_NO_OFFSET = datetime(2026, 10, 1, 9, 0)  # noqa: DTZ001


def test_an_aware_time_is_converted_to_utc() -> None:
    converted = as_utc(datetime(2026, 10, 1, 9, 0, tzinfo=SINGAPORE))

    assert converted == datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)
    assert converted.tzinfo is timezone.utc


def test_a_time_without_an_offset_is_read_as_business_time() -> None:
    assert as_utc(NINE_AM_NO_OFFSET) == datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)


def test_business_time_follows_the_configured_timezone(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(app.config, "APP_TIMEZONE", "Europe/London")  # UTC+1 in October

    assert as_utc(NINE_AM_NO_OFFSET) == datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)


def test_a_utc_time_is_shown_in_business_time() -> None:
    shown = to_business_time(datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc))

    assert (shown.hour, shown.minute) == (9, 0)
    assert shown.utcoffset() == timedelta(hours=8)


def test_business_time_for_display_follows_the_configured_timezone(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(app.config, "APP_TIMEZONE", "Europe/London")  # UTC+1 in October

    shown = to_business_time(datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc))

    assert shown.utcoffset() == timedelta(hours=1)
    assert (shown.hour, shown.minute) == (2, 0)
