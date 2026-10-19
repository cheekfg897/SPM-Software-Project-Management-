"""Unit tests for SCRUM-33 AC6: each venue arrangement is reassessed on its own.

Given an event has several venue arrangements, when a significant change is made,
each arrangement is reassessed separately and only the arrangements the change
affects are flagged (ADR-0094). The flags mirror SCRUM-58: a date or time change, or
a venue requirements change, leaves each live arrangement "requiring reconfirmation"
(AC1); attendance above the venue's capacity leaves it "no longer suitable", naming
capacity (AC2); a change touching none of these leaves every arrangement untouched
(AC4); each one is judged by its own occupancy, so a breakout room is not judged
against the whole event's attendance (AC5, SCRUM-93 AC3). Venue Staff are told
about each arrangement flagged (AC1).

The services run against ``db_session``. The event is the ``saved_event`` fixture's:
approved, coordinated by user 3, 80 attending, from 09:00 on 1 November 2026. Its
two arrangements are both approved: the Auditorium (capacity 100) holds everyone, and
the Breakout room (capacity 40) holds 30.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.events import services as event_services
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.notifications.services import NotificationKind, list_notifications_for_recipient
from app.modules.venue.models import Venue
from tests.venue.conftest import (
    COORDINATOR_ID,
    SECOND_PERIOD,
    VENUE_STAFF_ID,
    SavedEvent,
    approve_safety,
    decide,
    raise_booking,
    reload_event,
    reload_request,
)

pytestmark = pytest.mark.scrum_33

#: The day the edits are made, for the edit's "not in the past" rule.
EDIT_DAY = date(2026, 10, 1)
TIMING_REASON = "The event's date or time changed."
REQUIREMENTS_REASON = "The event's venue requirements changed."
CAPACITY_REASON = "Expected attendance of 150 exceeds the venue's capacity of 100."
RISE_REASON = (
    "The event's expected attendance rose from 80 to 90,"
    " above this arrangement's expected occupancy of 80."
)
RECONFIRM = "requires_reconfirmation"
UNSUITABLE = "no_longer_suitable"


def _edit(session: Session, event: EventRequest, payload: dict[str, Any]) -> None:
    """Edit ``event`` as its coordinator (SCRUM-33)."""
    event_services.update_event_request(
        COORDINATOR_ID, event.reference, payload, session=session, today=EDIT_DAY
    )


def _flags(session: Session, request_id: int) -> list[tuple[str, str]]:
    """The arrangement's reassessment flags as (kind, reason), oldest first."""
    rows = []
    for flag in reload_request(session, request_id).reassessment_flags:
        rows.append((flag.kind.value, flag.reason))
    return rows


def _venue_staff_notices() -> list[tuple[int, str | None]]:
    """What Venue Staff were told about significant changes, as (event id, detail)."""
    rows = []
    for notification in list_notifications_for_recipient(VENUE_STAFF_ID):
        if notification.kind is NotificationKind.SIGNIFICANT_CHANGE:
            rows.append((notification.event_request_id, notification.detail))
    return sorted(rows)


def _approved(venue: Venue, event: EventRequest, session: Session, **overrides: Any) -> int:
    """Raise a request for ``event`` at ``venue`` and approve it; return its id."""
    request = raise_booking(venue, event, session, **overrides)
    return decide(request.id, "approved", session).id


@pytest.fixture()
def auditorium(make_venue: Callable[..., Venue], save: Callable[..., None]) -> Venue:
    """A venue that holds 100."""
    saved = make_venue(name="Auditorium", capacity=100)
    save(saved)
    return saved


@pytest.fixture()
def breakout_room(make_venue: Callable[..., Venue], save: Callable[..., None]) -> Venue:
    """A venue that holds 40."""
    saved = make_venue(name="Breakout room", capacity=40)
    save(saved)
    return saved


@pytest.fixture()
def event(saved_users: list[User], saved_event: SavedEvent) -> EventRequest:
    """The approved event, 80 attending, with Venue Staff saved to be told."""
    return saved_event()


@pytest.fixture()
def main_id(db_session: Session, auditorium: Venue, event: EventRequest) -> int:
    """The approved Auditorium arrangement, for the event's whole audience of 80."""
    return _approved(auditorium, event, db_session)


@pytest.fixture()
def breakout_id(db_session: Session, breakout_room: Venue, event: EventRequest) -> int:
    """The approved Breakout room arrangement, in the afternoon, for 30 of them."""
    return _approved(breakout_room, event, db_session, expected_occupancy=30, **SECOND_PERIOD)


# --------------------------------------------------------------------------
# SCRUM-58 AC1 — a date or time change needs every booking reconfirmed
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"proposed_date": "2026-11-08"},
        {"end_date": "2026-11-03"},
        {"start_time": "10:00"},
        {"end_time": "18:00"},
    ],
    ids=["proposed-date", "end-date", "start-time", "end-time"],
)
def test_a_date_or_time_change_flags_every_arrangement_for_reconfirmation(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    breakout_id: int,
    payload: dict[str, Any],
) -> None:
    _edit(db_session, event, payload)

    assert _flags(db_session, main_id) == [(RECONFIRM, TIMING_REASON)]
    assert _flags(db_session, breakout_id) == [(RECONFIRM, TIMING_REASON)]


def test_a_confirmed_event_goes_back_to_approved_with_its_arrangements_flagged(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    """The withdrawn safety approval takes it back (AC7, ADR-0087)."""
    event.status = EventRequestStatus.CONFIRMED
    approve_safety(event, db_session)

    _edit(db_session, event, {"end_time": "18:00"})

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED
    assert _flags(db_session, main_id) == [(RECONFIRM, TIMING_REASON)]


# --------------------------------------------------------------------------
# SCRUM-58 AC2, AC5 — attendance is judged by each arrangement's own occupancy
# --------------------------------------------------------------------------


def test_attendance_above_capacity_flags_only_the_arrangement_holding_everyone(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    _edit(db_session, event, {"expected_attendance": 150})

    assert _flags(db_session, main_id) == [(UNSUITABLE, CAPACITY_REASON)]
    assert _flags(db_session, breakout_id) == []


def test_attendance_rising_within_capacity_asks_for_reconfirmation(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    _edit(db_session, event, {"expected_attendance": 90})

    assert _flags(db_session, main_id) == [(RECONFIRM, RISE_REASON)]
    assert _flags(db_session, breakout_id) == []


def test_a_fall_in_attendance_flags_nothing(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    _edit(db_session, event, {"expected_attendance": 60})

    assert _flags(db_session, main_id) == []
    assert _flags(db_session, breakout_id) == []


def test_an_arrangement_still_holding_everyone_after_a_fall_is_judged_on_the_next_rise(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    _edit(db_session, event, {"expected_attendance": 60})

    _edit(db_session, event, {"expected_attendance": 150})

    assert _flags(db_session, main_id) == [(UNSUITABLE, CAPACITY_REASON)]
    assert _flags(db_session, breakout_id) == []


@pytest.mark.parametrize("attendance", [95, 100], ids=["below-its-occupancy", "at-it"])
def test_an_arrangement_booked_for_more_than_the_audience_stands_while_it_holds_everyone(
    db_session: Session, auditorium: Venue, event: EventRequest, attendance: int
) -> None:
    roomy_id = _approved(auditorium, event, db_session, expected_occupancy=100)

    _edit(db_session, event, {"expected_attendance": attendance})

    assert _flags(db_session, roomy_id) == []


# --------------------------------------------------------------------------
# Venue requirements, several reasons at once, and SCRUM-58 AC4
# --------------------------------------------------------------------------


def test_a_venue_requirements_change_flags_every_arrangement_for_reconfirmation(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    _edit(db_session, event, {"venue_requirements": "Stage and step-free access"})

    assert _flags(db_session, main_id) == [(RECONFIRM, REQUIREMENTS_REASON)]
    assert _flags(db_session, breakout_id) == [(RECONFIRM, REQUIREMENTS_REASON)]


def test_one_change_gives_each_arrangement_only_the_reasons_that_apply_to_it(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    _edit(
        db_session,
        event,
        {"end_time": "18:00", "venue_requirements": "Stage", "expected_attendance": 150},
    )

    assert _flags(db_session, main_id) == [
        (RECONFIRM, TIMING_REASON),
        (RECONFIRM, REQUIREMENTS_REASON),
        (UNSUITABLE, CAPACITY_REASON),
    ]
    assert _flags(db_session, breakout_id) == [
        (RECONFIRM, TIMING_REASON),
        (RECONFIRM, REQUIREMENTS_REASON),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"description": "A new description"},
        {"equipment_requirements": "Four microphones"},
        {"internal_planning_notes": "Call the caterer"},
    ],
    ids=["description", "equipment-requirements", "internal-notes"],
)
def test_a_change_touching_no_venue_detail_leaves_every_arrangement_untouched(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    breakout_id: int,
    payload: dict[str, Any],
) -> None:
    _edit(db_session, event, payload)

    assert _flags(db_session, main_id) == []
    assert _flags(db_session, breakout_id) == []
    assert _venue_staff_notices() == []


# --------------------------------------------------------------------------
# Which arrangements can be flagged, and what the flag means once decided
# --------------------------------------------------------------------------


def test_a_pending_arrangement_is_flagged_and_a_rejected_one_is_not(
    db_session: Session,
    auditorium: Venue,
    breakout_room: Venue,
    event: EventRequest,
) -> None:
    pending = raise_booking(auditorium, event, db_session)
    rejected = raise_booking(
        breakout_room, event, db_session, expected_occupancy=30, **SECOND_PERIOD
    )
    decide(rejected.id, "rejected", db_session, reason="Closed that day.")

    _edit(db_session, event, {"end_time": "18:00"})

    assert _flags(db_session, pending.id) == [(RECONFIRM, TIMING_REASON)]
    assert _flags(db_session, rejected.id) == []


def test_a_flagged_arrangement_counts_as_flagged_only_while_it_is_live(
    db_session: Session, auditorium: Venue, event: EventRequest
) -> None:
    pending = raise_booking(auditorium, event, db_session)
    _edit(db_session, event, {"end_time": "18:00"})
    flagged_while_pending = reload_request(db_session, pending.id).is_flagged_after_change

    decide(pending.id, "rejected", db_session, reason="Closed that day.")

    assert flagged_while_pending is True
    assert reload_request(db_session, pending.id).is_flagged_after_change is False


def test_the_flags_are_saved_with_the_edit(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    _edit(db_session, event, {"end_time": "18:00"})

    db_session.rollback()

    assert _flags(db_session, main_id) == [(RECONFIRM, TIMING_REASON)]


# --------------------------------------------------------------------------
# SCRUM-58 AC1 — Venue Staff are told about each arrangement flagged
# --------------------------------------------------------------------------


def test_venue_staff_are_told_about_each_arrangement_flagged_and_why(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    _edit(db_session, event, {"end_time": "18:00", "expected_attendance": 150})

    assert _venue_staff_notices() == [
        (
            event.id,
            f"Venue arrangement {main_id} at Auditorium: {TIMING_REASON} {CAPACITY_REASON}",
        ),
        (event.id, f"Venue arrangement {breakout_id} at Breakout room: {TIMING_REASON}"),
    ]
