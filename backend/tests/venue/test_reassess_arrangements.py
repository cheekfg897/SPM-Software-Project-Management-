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

from app.common.errors import ConflictError, ValidationError
from app.modules.auth.models import User
from app.modules.events import services as event_services
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.notifications.services import NotificationKind, list_notifications_for_recipient
from app.modules.venue.models import (
    BookingRequestStatus,
    ReassessmentFlag,
    ReassessmentFlagKind,
    Venue,
)
from app.modules.venue.schemas import BookingRequestAsShown, VenueBookingRequestSchema
from tests.venue.conftest import (
    COORDINATOR_ID,
    SECOND_PERIOD,
    VENUE_STAFF_ID,
    SavedEvent,
    approve_safety,
    at,
    block,
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
#: The ``saved_users`` organiser who submitted the event.
ORGANISER_ID = 7
#: The morning of the day after the event starts, clear of every booking it has.
DAY_AFTER = {"starts_at": "2026-11-02T09:00:00+08:00", "ends_at": "2026-11-02T12:00:00+08:00"}
UNSUITABLE = "no_longer_suitable"

#: The statuses in which an arrangement still holds or asks for its venue (ADR-0094
#: decision 2), written out so the test doesn't copy the code's own list.
LIVE_STATUSES = [
    BookingRequestStatus.PENDING,
    BookingRequestStatus.CONFLICTING,
    BookingRequestStatus.APPROVED,
]
#: Every other status, built from the enum so a status added later is checked too. On
#: Hold is among them until the SCRUM-75 follow-up flags it (ADR-0094 decision 2).
UNFLAGGED_STATUSES = [status for status in BookingRequestStatus if status not in LIVE_STATUSES]


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


def _set_status(session: Session, request_id: int, status: BookingRequestStatus) -> None:
    """Put the arrangement straight into ``status``, whatever the flow allows."""
    reload_request(session, request_id).status = status
    session.commit()


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


def test_an_event_in_safety_review_goes_back_to_approved_with_its_arrangements_flagged(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    """The withdrawn safety approval takes it back (AC7, ADR-0087).

    A Confirmed event can't be edited directly (AC8), so Safety Review, where every
    arrangement is already approved, is the last status an edit reaches (ADR-0094
    decision 11, ADR-0101).
    """
    event.status = EventRequestStatus.SAFETY_REVIEW
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


@pytest.mark.parametrize("status", LIVE_STATUSES, ids=lambda status: status.value)
def test_every_live_arrangement_is_flagged_and_named_to_venue_staff(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    breakout_id: int,
    status: BookingRequestStatus,
) -> None:
    _set_status(db_session, breakout_id, status)

    _edit(db_session, event, {"end_time": "18:00"})

    assert _flags(db_session, breakout_id) == [(RECONFIRM, TIMING_REASON)]
    assert (
        event.id,
        f"Venue arrangement {breakout_id} at Breakout room: {TIMING_REASON}",
    ) in _venue_staff_notices()


@pytest.mark.parametrize("status", UNFLAGGED_STATUSES, ids=lambda status: status.value)
def test_an_arrangement_in_any_other_status_is_neither_flagged_nor_named_to_venue_staff(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    breakout_id: int,
    status: BookingRequestStatus,
) -> None:
    """The live arrangement beside it is the decoy that shows the edit did reassess."""
    _set_status(db_session, breakout_id, status)

    _edit(db_session, event, {"end_time": "18:00"})

    assert _flags(db_session, breakout_id) == []
    assert _venue_staff_notices() == [
        (event.id, f"Venue arrangement {main_id} at Auditorium: {TIMING_REASON}")
    ]


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


# --------------------------------------------------------------------------
# SCRUM-58 AC3 — a flagged arrangement holds the event back, and is named
# --------------------------------------------------------------------------


def test_safety_review_is_refused_naming_only_the_arrangement_flagged(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    """SCRUM-97 shares the venue check with confirmation (ADR-0051)."""
    _edit(db_session, event, {"expected_attendance": 150})

    with pytest.raises(event_services.SafetyReviewNotAllowedError) as refusal:
        event_services.submit_for_safety_review(COORDINATOR_ID, event.reference, session=db_session)

    assert refusal.value.details == {
        "venue_arrangements": [
            f"Venue arrangement {main_id} is flagged (no longer suitable): {CAPACITY_REASON}"
        ]
    }


def test_safety_review_names_every_reason_each_arrangement_was_flagged(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    _edit(db_session, event, {"end_time": "18:00", "expected_attendance": 150})

    with pytest.raises(event_services.SafetyReviewNotAllowedError) as refusal:
        event_services.submit_for_safety_review(COORDINATOR_ID, event.reference, session=db_session)

    assert refusal.value.details == {
        "venue_arrangements": [
            f"Venue arrangement {main_id} is flagged (requires reconfirmation): {TIMING_REASON}",
            f"Venue arrangement {main_id} is flagged (no longer suitable): {CAPACITY_REASON}",
            f"Venue arrangement {breakout_id} is flagged (requires reconfirmation): "
            f"{TIMING_REASON}",
        ]
    }


def test_confirmation_is_refused_while_an_arrangement_is_flagged(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    _edit(db_session, event, {"end_time": "18:00"})
    event.status = EventRequestStatus.SAFETY_REVIEW
    approve_safety(event, db_session)

    with pytest.raises(event_services.EventConfirmationNotAllowedError) as refusal:
        event_services.confirm_event_request(COORDINATOR_ID, event.reference, session=db_session)

    reconfirm = f"is flagged (requires reconfirmation): {TIMING_REASON}"
    assert refusal.value.details == {
        "venue_arrangements": [
            f"Venue arrangement {main_id} {reconfirm}",
            f"Venue arrangement {breakout_id} {reconfirm}",
        ]
    }


# --------------------------------------------------------------------------
# The coordinator's and Venue Staff's lists show each flag and its reason
# --------------------------------------------------------------------------


def test_a_flagged_request_shows_each_reason(shown: BookingRequestAsShown) -> None:
    shown.request.status = BookingRequestStatus.APPROVED
    shown.request.reassessment_flags = [
        ReassessmentFlag(kind=ReassessmentFlagKind.REQUIRES_RECONFIRMATION, reason=TIMING_REASON),
        ReassessmentFlag(kind=ReassessmentFlagKind.NO_LONGER_SUITABLE, reason=CAPACITY_REASON),
    ]

    body = VenueBookingRequestSchema().dump(shown)

    assert body["flagged_after_change"] is True
    assert body["reassessment_flags"] == [
        {"kind": RECONFIRM, "reason": TIMING_REASON},
        {"kind": UNSUITABLE, "reason": CAPACITY_REASON},
    ]


def test_a_request_no_change_flagged_shows_no_flags(shown: BookingRequestAsShown) -> None:
    body = VenueBookingRequestSchema().dump(shown)

    assert body["flagged_after_change"] is False
    assert body["reassessment_flags"] == []


# --------------------------------------------------------------------------
# A replacement releases a flagged arrangement (SCRUM-92 AC6, AC7, ADR-0094)
# --------------------------------------------------------------------------


def test_a_change_flagged_arrangement_is_replaced_at_its_own_venue_at_a_new_time(
    db_session: Session, auditorium: Venue, event: EventRequest, main_id: int
) -> None:
    """A replacement clears a change flag (Product Owner 25 Oct, 6.4; ADR-0100).

    The different-venue rule is for a venue that became unavailable (SCRUM-92), so the
    event's own venue at its new time is accepted, and approving it releases the
    original.
    """
    _edit(db_session, event, {"end_time": "18:00"})

    replacement = raise_booking(
        auditorium, event, db_session, replaces_request_id=main_id, **SECOND_PERIOD
    )
    decide(replacement.id, "approved", db_session)

    assert replacement.venue_id == auditorium.id
    assert reload_request(db_session, main_id).status is BookingRequestStatus.RELEASED


@pytest.mark.scrum_92
def test_a_replacement_at_its_own_venue_is_refused_once_that_venue_is_unavailable_too(
    db_session: Session, auditorium: Venue, event: EventRequest, main_id: int
) -> None:
    """Flagged both ways, the different-venue rule wins (SCRUM-92 AC6, ADR-0100).

    The change flag alone would let the event's own venue be used at its new time, but
    a block over the original leaves that venue unavailable, so it is refused on
    ``venue_id`` and nothing is raised.
    """
    _edit(db_session, event, {"end_time": "18:00"})
    block(auditorium, at(10), at(11), db_session)

    with pytest.raises(ValidationError) as refusal:
        raise_booking(auditorium, event, db_session, replaces_request_id=main_id, **SECOND_PERIOD)

    assert refusal.value.details == {
        "venue_id": ["A replacement must be at a different venue from the one it replaces."]
    }
    original = reload_request(db_session, main_id)
    assert original.is_flagged_after_change is True
    assert original.needs_alternative_venue is True


@pytest.mark.scrum_92
def test_a_replacement_at_another_venue_keeps_the_period_once_the_venue_is_unavailable_too(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    auditorium: Venue,
    event: EventRequest,
    main_id: int,
) -> None:
    """Flagged both ways, the period is locked too (SCRUM-92 AC6, ADR-0108).

    The change flag alone would let the replacement take the new time, but a block
    over the original makes it a replacement for a venue that became unavailable.
    """
    _edit(db_session, event, {"end_time": "18:00"})
    block(auditorium, at(10), at(11), db_session)
    great_hall = make_venue(name="Great Hall", capacity=200)
    save(great_hall)

    with pytest.raises(ValidationError) as refusal:
        raise_booking(great_hall, event, db_session, replaces_request_id=main_id, **SECOND_PERIOD)

    locked = (
        "A replacement keeps the date and times of the booking it replaces:"
        " 2026-11-01 09:00 to 2026-11-01 12:00."
    )
    assert refusal.value.details == {"starts_at": [locked], "ends_at": [locked]}


@pytest.mark.scrum_92
def test_a_change_flagged_replacement_tells_the_organiser_nothing_though_the_event_went_back(
    db_session: Session,
    breakout_room: Venue,
    auditorium: Venue,
    event: EventRequest,
    main_id: int,
    breakout_id: int,
) -> None:
    """SCRUM-92 AC9 is about AC7's replacement, for a venue that became unavailable.

    The breakout room's block sent the Confirmed event back, but the Auditorium
    arrangement it replaces was only flagged by the later change, so the Organiser
    hears nothing of its approval (ADR-0108).
    """
    event.status = EventRequestStatus.CONFIRMED
    db_session.commit()
    block(breakout_room, at(13), at(14), db_session)
    _edit(db_session, event, {"end_time": "18:00"})
    replacement = raise_booking(
        auditorium, event, db_session, replaces_request_id=main_id, **DAY_AFTER
    )

    decide(replacement.id, "approved", db_session)

    kinds = [notice.kind for notice in list_notifications_for_recipient(ORGANISER_ID)]
    assert NotificationKind.ALTERNATIVE_VENUE_NEEDED in kinds
    assert NotificationKind.REPLACEMENT_VENUE_APPROVED not in kinds


def test_a_change_flagged_replacement_overlapping_its_own_booking_is_refused_at_approval(
    db_session: Session, auditorium: Venue, event: EventRequest, main_id: int
) -> None:
    """The original's booking still holds the venue until the replacement is approved.

    So an overlapping replacement at the same venue clashes with it (ADR-0045,
    ADR-0094 "Not covered here"), and the original stands, still flagged.
    """
    _edit(db_session, event, {"end_time": "18:00"})
    overlapping = {
        "starts_at": "2026-11-01T10:00:00+08:00",
        "ends_at": "2026-11-01T13:00:00+08:00",
    }
    replacement = raise_booking(
        auditorium, event, db_session, replaces_request_id=main_id, **overlapping
    )

    with pytest.raises(ConflictError):
        decide(replacement.id, "approved", db_session)

    original = reload_request(db_session, main_id)
    assert original.status is BookingRequestStatus.APPROVED
    assert original.is_flagged_after_change is True


def test_a_replacement_releases_an_arrangement_flagged_after_a_change(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    event: EventRequest,
    main_id: int,
    breakout_id: int,
) -> None:
    _edit(db_session, event, {"expected_attendance": 150})
    great_hall = make_venue(name="Great Hall", capacity=200)
    save(great_hall)

    replacement = raise_booking(great_hall, event, db_session, replaces_request_id=main_id)
    decide(replacement.id, "approved", db_session)

    released = reload_request(db_session, main_id)
    assert released.status is BookingRequestStatus.RELEASED
    assert released.is_flagged_after_change is False
    reviewed = event_services.submit_for_safety_review(
        COORDINATOR_ID, event.reference, session=db_session
    )
    assert reviewed.status is EventRequestStatus.SAFETY_REVIEW
