"""Unit tests for SCRUM-26 — View a venue's availability calendar.

Same DB-mocked-session style as the rest of Sprint 1/2. Route bodies aren't
HTTP-tested this sprint (see auth's own testing note), but the
``@requires_role(*INTERNAL_ROLES)`` wiring on the calendar route is cheap and
meaningful to check directly via the decorator's ``allowed_roles``
attribute, without a request context or a real DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.common.decorators import normalise_roles
from app.common.errors import NotFoundError, ValidationError
from app.modules.auth.permissions import INTERNAL_ROLES, Role
from app.modules.venue import services
from app.modules.venue.models import BookingStatus

pytestmark = pytest.mark.story_venue_calendar


def _scalars(items: list) -> MagicMock:
    result = MagicMock()
    result.all.return_value = items
    return result


RANGE_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
RANGE_END = datetime(2026, 1, 2, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# AC1/AC2 — bookings and blocks both appear as unavailable, sorted
# --------------------------------------------------------------------------


def test_calendar_includes_confirmed_booking_and_block_sorted_by_start(
    mock_session, make_venue, make_booking, make_venue_block
) -> None:
    venue = make_venue()
    booking = make_booking(
        venue_id=venue.id,
        start_time=datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc),
        status=BookingStatus.CONFIRMED,
    )
    block = make_venue_block(
        venue_id=venue.id,
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    )
    mock_session.get.return_value = venue
    mock_session.scalars.side_effect = [_scalars([booking]), _scalars([block])]

    entries = services.get_venue_calendar(
        venue.id, RANGE_START, RANGE_END, viewer_role=Role.VENUE_STAFF, session=mock_session
    )

    assert [e["kind"] for e in entries] == ["block", "confirmed_booking"]
    assert entries[0]["start_time"] < entries[1]["start_time"]


def test_calendar_marks_tentative_booking_distinctly(mock_session, make_venue, make_booking) -> None:
    venue = make_venue()
    booking = make_booking(venue_id=venue.id, status=BookingStatus.TENTATIVE)
    mock_session.get.return_value = venue
    mock_session.scalars.side_effect = [_scalars([booking]), _scalars([])]

    entries = services.get_venue_calendar(
        venue.id, RANGE_START, RANGE_END, viewer_role=Role.VENUE_STAFF, session=mock_session
    )

    assert entries[0]["kind"] == "tentative_hold"


def test_calendar_unknown_venue_is_not_found(mock_session) -> None:
    mock_session.get.return_value = None

    with pytest.raises(NotFoundError):
        services.get_venue_calendar(
            999, RANGE_START, RANGE_END, viewer_role=Role.VENUE_STAFF, session=mock_session
        )


# --------------------------------------------------------------------------
# AC3 — reason detail is role-gated
# --------------------------------------------------------------------------


def test_venue_staff_sees_full_block_reason(mock_session, make_venue, make_venue_block) -> None:
    venue = make_venue()
    block = make_venue_block(venue_id=venue.id, reason="Fire alarm inspection")
    mock_session.get.return_value = venue
    mock_session.scalars.side_effect = [_scalars([]), _scalars([block])]

    entries = services.get_venue_calendar(
        venue.id, RANGE_START, RANGE_END, viewer_role=Role.VENUE_STAFF, session=mock_session
    )

    assert entries[0]["reason"] == "Fire alarm inspection"


@pytest.mark.parametrize("role", [Role.EVENT_COORDINATOR, Role.TECHNICAL_SUPPORT_STAFF])
def test_non_venue_staff_internal_roles_see_coarse_block_reason(
    mock_session, make_venue, make_venue_block, role: Role
) -> None:
    venue = make_venue()
    block = make_venue_block(venue_id=venue.id, reason="Fire alarm inspection")
    mock_session.get.return_value = venue
    mock_session.scalars.side_effect = [_scalars([]), _scalars([block])]

    entries = services.get_venue_calendar(
        venue.id, RANGE_START, RANGE_END, viewer_role=role, session=mock_session
    )

    assert entries[0]["reason"] == "maintenance"
    assert "Fire alarm" not in entries[0]["reason"]


def test_venue_staff_sees_linked_event_for_booking(mock_session, make_venue, make_booking) -> None:
    venue = make_venue()
    booking = make_booking(venue_id=venue.id, event_id=42, status=BookingStatus.CONFIRMED)
    mock_session.get.return_value = venue
    mock_session.scalars.side_effect = [_scalars([booking]), _scalars([])]

    entries = services.get_venue_calendar(
        venue.id, RANGE_START, RANGE_END, viewer_role=Role.VENUE_STAFF, session=mock_session
    )

    assert "42" in entries[0]["reason"]


def test_event_coordinator_sees_coarse_booking_reason(mock_session, make_venue, make_booking) -> None:
    venue = make_venue()
    booking = make_booking(venue_id=venue.id, event_id=42, status=BookingStatus.CONFIRMED)
    mock_session.get.return_value = venue
    mock_session.scalars.side_effect = [_scalars([booking]), _scalars([])]

    entries = services.get_venue_calendar(
        venue.id, RANGE_START, RANGE_END, viewer_role=Role.EVENT_COORDINATOR, session=mock_session
    )

    assert entries[0]["reason"] == "booking"


# --------------------------------------------------------------------------
# AC4 — Event Organisers and Attendees cannot open the calendar
# --------------------------------------------------------------------------


def test_calendar_route_only_allows_internal_roles() -> None:
    from app.modules.venue.routes import get_calendar

    assert get_calendar.allowed_roles == normalise_roles(INTERNAL_ROLES)
    assert "event_organiser" not in get_calendar.allowed_roles
    assert "attendee" not in get_calendar.allowed_roles


# --------------------------------------------------------------------------
# Supporting infra — recording a block so AC2 ("blocked periods appear as
# unavailable") has a path to exercise via the API. Restricted to Venue
# Staff the same way catalogue edits are (SCRUM-25 AC3).
# --------------------------------------------------------------------------


def test_create_block_persists_against_the_venue(mock_session, make_venue) -> None:
    venue = make_venue()
    mock_session.get.return_value = venue

    block = services.create_block(
        venue.id,
        {
            "start_time": "2026-01-05T09:00:00+00:00",
            "end_time": "2026-01-05T11:00:00+00:00",
            "reason": "Carpet cleaning",
        },
        session=mock_session,
    )

    assert block.venue_id == venue.id
    assert block.reason == "Carpet cleaning"
    mock_session.add.assert_called_once_with(block)
    mock_session.commit.assert_called_once()


def test_create_block_rejects_end_before_start(mock_session, make_venue) -> None:
    venue = make_venue()
    mock_session.get.return_value = venue

    with pytest.raises(ValidationError):
        services.create_block(
            venue.id,
            {"start_time": "2026-01-05T11:00:00+00:00", "end_time": "2026-01-05T09:00:00+00:00"},
            session=mock_session,
        )


def test_create_block_unknown_venue_is_not_found(mock_session) -> None:
    mock_session.get.return_value = None

    with pytest.raises(NotFoundError):
        services.create_block(
            999,
            {"start_time": "2026-01-05T09:00:00+00:00", "end_time": "2026-01-05T11:00:00+00:00"},
            session=mock_session,
        )
