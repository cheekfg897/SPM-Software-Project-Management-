"""Unit tests for SCRUM-67 — Record setup and turnaround time for a venue.

AC5 ("Only Venue Staff can change these values") is enforced by the
``@requires_role(Role.VENUE_STAFF)`` decorator on the ``PATCH`` route (see
``routes.py``) and is exercised by ``app.common.decorators`` tests already —
nothing venue-specific to unit test there.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.auth.permissions import Role
from app.modules.venue import services
from app.modules.venue.models import BookingStatus

pytestmark = pytest.mark.story_venue_setup_turnaround


def _scalars(items: list) -> MagicMock:
    result = MagicMock()
    result.all.return_value = items
    return result


# --------------------------------------------------------------------------
# AC1/AC2 — recorded per venue, default when unset
# --------------------------------------------------------------------------


def test_effective_window_extends_by_setup_and_turnaround(make_venue) -> None:
    venue = make_venue(setup_minutes=10, turnaround_minutes=20)
    start = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)

    buf_start, buf_end = services._effective_window(venue, start, end)

    assert buf_start == start - timedelta(minutes=10)
    assert buf_end == end + timedelta(minutes=20)


# --------------------------------------------------------------------------
# AC3 — calendar, search and conflict detection all use the buffered window
# --------------------------------------------------------------------------


def test_calendar_entry_reflects_venue_buffers(mock_session, make_venue, make_booking) -> None:
    venue = make_venue(setup_minutes=15, turnaround_minutes=45)
    booking = make_booking(
        venue_id=venue.id,
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        status=BookingStatus.CONFIRMED,
    )
    mock_session.get.return_value = venue
    mock_session.scalars.side_effect = [_scalars([booking]), _scalars([])]

    entries = services.get_venue_calendar(
        venue.id,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        viewer_role=Role.VENUE_STAFF,
        session=mock_session,
    )

    assert len(entries) == 1
    assert entries[0]["start_time"] == booking.start_time - timedelta(minutes=15)
    assert entries[0]["end_time"] == booking.end_time + timedelta(minutes=45)


def test_search_excludes_venue_when_buffer_creates_conflict(mock_session, make_venue, make_booking) -> None:
    """Without the buffer these slots wouldn't overlap; with it, they do (AC3)."""
    venue = make_venue(capacity=50, setup_minutes=30, turnaround_minutes=30)
    existing = make_booking(
        venue_id=venue.id,
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        status=BookingStatus.CONFIRMED,
    )
    # Requested slot starts 15 minutes after the existing booking ends —
    # free without a buffer, inside the 30-minute turnaround with one.
    requested_start = datetime(2026, 1, 1, 10, 15, tzinfo=timezone.utc)
    requested_end = datetime(2026, 1, 1, 11, 15, tzinfo=timezone.utc)

    mock_session.scalars.side_effect = [_scalars([venue]), _scalars([existing]), _scalars([])]

    results = services.search_venues(
        {
            "start_time": requested_start.isoformat(),
            "end_time": requested_end.isoformat(),
            "min_capacity": 10,
        },
        session=mock_session,
    )

    assert results == []


# --------------------------------------------------------------------------
# AC4 — changing buffers doesn't invalidate confirmed bookings, but reports overlaps
# --------------------------------------------------------------------------


def test_update_turnaround_reports_newly_overlapping_confirmed_bookings(
    mock_session, make_venue, make_booking
) -> None:
    venue = make_venue(setup_minutes=0, turnaround_minutes=0)
    booking_a = make_booking(
        venue_id=venue.id,
        booking_id=1,
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        status=BookingStatus.CONFIRMED,
    )
    # Starts 5 minutes after booking_a ends — fine with a 0-minute turnaround.
    booking_b = make_booking(
        venue_id=venue.id,
        booking_id=2,
        start_time=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
        status=BookingStatus.CONFIRMED,
    )
    mock_session.get.return_value = venue
    mock_session.scalars.return_value = _scalars([booking_a, booking_b])

    updated, warnings = services.update_venue(
        venue.id, {"turnaround_minutes": 10}, session=mock_session
    )

    assert updated.turnaround_minutes == 10
    assert len(warnings) == 1
    assert set(warnings[0]["booking_ids"]) == {1, 2}
    # Neither booking is touched/invalidated — status stays confirmed.
    assert booking_a.status == BookingStatus.CONFIRMED
    assert booking_b.status == BookingStatus.CONFIRMED


def test_update_without_buffer_change_reports_no_overlaps(mock_session, make_venue) -> None:
    venue = make_venue()
    mock_session.get.return_value = venue

    _, warnings = services.update_venue(venue.id, {"capacity": 200}, session=mock_session)

    assert warnings == []
    mock_session.scalars.assert_not_called()
