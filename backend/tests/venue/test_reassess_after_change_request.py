"""Unit tests for SCRUM-58 "Reassess venue bookings after an approved change request".

When the coordinator approves a change request (SCRUM-57), each of the event's venue
bookings is checked again, by the same checks as the coordinator's direct edit
(SCRUM-33 AC6, ADR-0094, ADR-0129):

- AC1: a date or time change marks every booking Requires reconfirmation, and Venue
  Staff are told.
- AC2: attendance above a venue's capacity marks that booking No longer suitable.
- AC3: the event can't go on while a booking is marked; Venue Staff resolve it
  (SCRUM-59).
- AC4: a change to anything else leaves every booking untouched.
- AC5: each booking is checked on its own, as the story's table says.
- AC6: a safety approval is withdrawn by a significant change (SCRUM-33 AC7).
- AC7: a Confirmed event goes back to Approved through that withdrawal.

AC8, the journey through the routes, is in
``tests/e2e/test_change_request_venue_journey.py``.

The services run against ``db_session``. The event is the ``saved_event`` fixture's:
approved, coordinated by user 3, organiser 7's, 80 attending, from 09:00 on 1 November
2026 to 17:30 the next day. Its two bookings are approved: the Auditorium (capacity 100)
holds everyone, and the Breakout room (capacity 40) holds 30. ``today`` is pinned to
``EDIT_DAY``, so the requested dates are never in the past.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events import services as event_services
from app.modules.events.models import (
    ChangeRequestStatus,
    EventChangeRequest,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.notifications.services import NotificationKind, list_notifications_for_recipient
from app.modules.venue import services as venue_services
from app.modules.venue.models import BookingRequestStatus, Venue
from tests.events.cases import lose_connection
from tests.venue.conftest import (
    COORDINATOR_ID,
    EDIT_DAY,
    SECOND_PERIOD,
    VENUE_STAFF_ID,
    SavedEvent,
    approve_safety,
    approved_arrangement,
    decide,
    edit_event,
    flags_on,
    history_entries,
    raise_booking,
    reload_event,
    reload_request,
)

pytestmark = pytest.mark.scrum_58

ORGANISER_ID = 7
SAFETY_OFFICER_ID = 21
RECONFIRM = "requires_reconfirmation"
UNSUITABLE = "no_longer_suitable"
TIMING_REASON = "The event's date or time changed."
REQUIREMENTS_REASON = "The event's venue requirements changed."
CAPACITY_REASON = "Expected attendance of 150 exceeds the venue's capacity of 100."
TIMING_FLAG = (RECONFIRM, TIMING_REASON)
REQUIREMENTS_FLAG = (RECONFIRM, REQUIREMENTS_REASON)
CAPACITY_FLAG = (UNSUITABLE, CAPACITY_REASON)
BACK_IN_PLANNING = "It is back in planning until it can be sent to Safety Review again."
REJECT = {"outcome": "rejected", "reason": "The hall is taken that week."}

#: Each field of the event's date or time, asked for on its own, by the smallest of
#: amounts where the story says the size doesn't matter (AC1).
TIMING_CHANGES = [
    pytest.param({"proposed_date": "2026-11-08"}, id="proposed-date"),
    pytest.param({"end_date": "2026-11-03"}, id="end-date"),
    pytest.param({"start_time": "09:05"}, id="start-time-five-minutes"),
    pytest.param({"end_time": "17:35"}, id="end-time-five-minutes"),
]

#: One changed value for each significant field, and the fields the withdrawal names: a
#: new proposed date moves the end date with it (SCRUM-33 AC2, AC7).
SIGNIFICANT_CHANGES = [
    pytest.param({"proposed_date": "2026-11-08"}, ["proposed_date", "end_date"], id="date"),
    pytest.param({"end_date": "2026-11-03"}, ["end_date"], id="end-date"),
    pytest.param({"start_time": "10:00"}, ["start_time"], id="start-time"),
    pytest.param({"end_time": "18:00"}, ["end_time"], id="end-time"),
    pytest.param({"expected_attendance": 81}, ["expected_attendance"], id="attendance-rises"),
    pytest.param({"expected_attendance": 60}, ["expected_attendance"], id="attendance-falls"),
    pytest.param({"venue_requirements": "A stage"}, ["venue_requirements"], id="venue-needs"),
    pytest.param({"equipment_requirements": "4 mics"}, ["equipment_requirements"], id="equipment"),
]

#: What the story calls anything else (AC4), each on its own.
OTHER_CHANGES = [
    pytest.param({"programme_notes": "A panel is added."}, id="programme-information"),
    pytest.param({"equipment_requirements": "4 mics"}, id="equipment"),
]
NOT_SIGNIFICANT = {"programme_notes": "A panel is added."}
MOVE_START = {"start_time": "10:00"}


def _rise_reason(new: int) -> str:
    """Why the Auditorium, booked for all 80, needs reconfirming for ``new`` people."""
    return (
        f"The event's expected attendance rose from 80 to {new},"
        " above this arrangement's expected occupancy of 80."
    )


def _raise_change(session: Session, event: EventRequest, change: dict[str, Any]) -> int:
    """Raise ``change`` as the event's Organiser; return the change request's id."""
    raised = event_services.raise_change_request(
        ORGANISER_ID,
        event.reference,
        {**change, "reason": "The keynote moved."},
        session=session,
        today=EDIT_DAY,
    )
    return raised.id


def _decide_change(
    session: Session, event: EventRequest, change_request_id: int, decision: dict[str, Any]
) -> None:
    """Decide the change request as the event's coordinator."""
    event_services.decide_change_request(
        COORDINATOR_ID,
        event.reference,
        change_request_id,
        decision,
        session=session,
        today=EDIT_DAY,
    )


def _approve_change(session: Session, event: EventRequest, change: dict[str, Any]) -> None:
    """Raise ``change`` as the Organiser and approve it as the coordinator."""
    change_request_id = _raise_change(session, event, change)
    _decide_change(session, event, change_request_id, {"outcome": "approved"})


def _notices_to(user_id: int, kind: NotificationKind) -> list[tuple[int, str | None]]:
    """What ``user_id`` was told of ``kind``, as (event id, detail), sorted."""
    rows = []
    for notification in list_notifications_for_recipient(user_id):
        if notification.kind is kind:
            rows.append((notification.event_request_id, notification.detail))
    return sorted(rows)


def _venue_staff_notices() -> list[tuple[int, str | None]]:
    """What Venue Staff were told about significant changes."""
    return _notices_to(VENUE_STAFF_ID, NotificationKind.SIGNIFICANT_CHANGE)


def _withdrawals(session: Session, event: EventRequest) -> list[tuple[int | None, Any]]:
    """The event's ``safety_approval_withdrawn`` entries, as (actor id, details)."""
    withdrawals = []
    for entry in history_entries(session, event.id):
        if entry.kind is EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN:
            withdrawals.append((entry.actor_id, entry.details))
    return withdrawals


def _has_approval(session: Session, event: EventRequest) -> bool:
    return event_services.has_safety_approval(event.id, session=session)


def _lose_every_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every notice fail, so none of their commits can hide a missing one."""
    monkeypatch.setattr(event_services, "notify_users", lose_connection)
    monkeypatch.setattr(venue_services, "notify_users", lose_connection)


def _reconfirm_as_listed(session: Session, request_id: int) -> None:
    """Reconfirm the booking for the period the list pre-fills (SCRUM-59 AC2)."""
    for flagged in venue_services.list_flagged_bookings(session=session):
        if flagged.shown.request.id == request_id:
            period = flagged.reconfirm_with
            payload = {
                "starts_at": period.starts_at.isoformat(),
                "ends_at": period.ends_at.isoformat(),
            }
            venue_services.reconfirm_flagged_booking(
                request_id, payload, reconfirmed_by=VENUE_STAFF_ID, session=session
            )
            return
    raise AssertionError(f"booking {request_id} is not listed")


@pytest.fixture()
def event(saved_users: list[User], saved_event: SavedEvent, db_session: Session) -> EventRequest:
    """The approved event, filed under the organisation of its Organiser (SCRUM-56)."""
    saved = saved_event()
    saved.organisation_id = 3
    db_session.commit()
    return saved


@pytest.fixture()
def main_id(db_session: Session, auditorium: Venue, event: EventRequest) -> int:
    """The approved Auditorium booking, for the event's whole audience of 80."""
    return approved_arrangement(auditorium, event, db_session)


@pytest.fixture()
def breakout_id(db_session: Session, breakout_room: Venue, event: EventRequest) -> int:
    """The approved Breakout room booking, in the afternoon, for 30 of them."""
    return approved_arrangement(
        breakout_room, event, db_session, expected_occupancy=30, **SECOND_PERIOD
    )


@pytest.fixture()
def safety_officer(make_user: Callable[..., User], save: Callable[..., None]) -> User:
    """A Safety Officer, to be told of a change made in Safety Review."""
    officer = make_user(
        email="safety21@example.com", role=Role.SAFETY_OFFICER, user_id=SAFETY_OFFICER_ID
    )
    save(officer)
    return officer


@pytest.fixture()
def passed_safety_check(db_session: Session, event: EventRequest) -> Callable[..., None]:
    """Put the event in a status with the Safety Officer's approval on its history."""

    def _pass(status: EventRequestStatus) -> None:
        event.status = status
        approve_safety(event, db_session)

    return _pass


# --------------------------------------------------------------------------
# AC1 — a date or time change marks every booking and tells Venue Staff
# --------------------------------------------------------------------------


@pytest.mark.parametrize("change", TIMING_CHANGES)
def test_an_approved_date_or_time_change_marks_every_booking_for_reconfirmation(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    breakout_id: int,
    change: dict[str, Any],
) -> None:
    _approve_change(db_session, event, change)

    assert flags_on(db_session, main_id) == [TIMING_FLAG]
    assert flags_on(db_session, breakout_id) == [TIMING_FLAG]
    assert reload_request(db_session, main_id).is_flagged_after_change is True
    assert reload_request(db_session, main_id).status is BookingRequestStatus.APPROVED


def test_venue_staff_are_told_of_each_booking_marked_and_why(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    _approve_change(db_session, event, {"end_time": "18:00", "expected_attendance": 150})

    assert _venue_staff_notices() == [
        (
            event.id,
            f"Venue arrangement {main_id} at Auditorium: {TIMING_REASON} {CAPACITY_REASON}",
        ),
        (event.id, f"Venue arrangement {breakout_id} at Breakout room: {TIMING_REASON}"),
    ]


def test_the_coordinator_who_approved_it_is_not_told_of_the_marks(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    """ADR-0094 decision 7: they made the change, and the list shows the marks."""
    _approve_change(db_session, event, MOVE_START)

    assert _notices_to(COORDINATOR_ID, NotificationKind.SIGNIFICANT_CHANGE) == []


def test_the_marks_are_committed_even_when_every_notice_fails(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The notices commit too, so with them gone only the decision's commit is left."""
    _lose_every_notice(monkeypatch)

    _approve_change(db_session, event, MOVE_START)
    db_session.rollback()

    assert flags_on(db_session, main_id) == [TIMING_FLAG]


def test_the_change_is_not_saved_if_its_bookings_cant_be_marked(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The change, the marks and the decision share one commit (ADR-0094 decision 7)."""

    def _marking_fails(*_args: Any, **_kwargs: Any) -> list[str]:
        raise RuntimeError("the bookings could not be marked")

    monkeypatch.setattr(venue_services, "flag_arrangements_after_change", _marking_fails)

    with pytest.raises(RuntimeError):
        _approve_change(db_session, event, MOVE_START)
    db_session.rollback()

    assert reload_event(db_session, event.id).start_time.hour == 9
    change_request = db_session.query(EventChangeRequest).one()
    assert change_request.status is ChangeRequestStatus.PENDING


# --------------------------------------------------------------------------
# AC2, AC5 — each booking is checked on its own, as the story's table says
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "main_flags", "breakout_flags"),
    [
        pytest.param({"start_time": "09:05"}, [TIMING_FLAG], [TIMING_FLAG], id="time-any-amount"),
        pytest.param(
            {"venue_requirements": "A stage"},
            [REQUIREMENTS_FLAG],
            [REQUIREMENTS_FLAG],
            id="venue-requirements",
        ),
        pytest.param({"expected_attendance": 150}, [CAPACITY_FLAG], [], id="above-capacity"),
        pytest.param(
            {"expected_attendance": 101},
            [(UNSUITABLE, "Expected attendance of 101 exceeds the venue's capacity of 100.")],
            [],
            id="one-above-capacity",
        ),
        pytest.param(
            {"expected_attendance": 100},
            [(RECONFIRM, _rise_reason(100))],
            [],
            id="exactly-at-capacity",
        ),
        pytest.param(
            {"expected_attendance": 81},
            [(RECONFIRM, _rise_reason(81))],
            [],
            id="one-above-what-was-booked",
        ),
        pytest.param({"expected_attendance": 79}, [], [], id="falls-by-one"),
        pytest.param({"expected_attendance": 25}, [], [], id="falls-below-the-smaller-room"),
    ],
)
def test_each_booking_is_checked_on_its_own(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    breakout_id: int,
    change: dict[str, Any],
    main_flags: list[tuple[str, str]],
    breakout_flags: list[tuple[str, str]],
) -> None:
    _approve_change(db_session, event, change)

    assert flags_on(db_session, main_id) == main_flags
    assert flags_on(db_session, breakout_id) == breakout_flags


def test_attendance_staying_within_what_was_booked_leaves_every_booking_untouched(
    db_session: Session, auditorium: Venue, event: EventRequest, breakout_id: int
) -> None:
    roomy_id = approved_arrangement(auditorium, event, db_session, expected_occupancy=100)

    _approve_change(db_session, event, {"expected_attendance": 100})

    assert flags_on(db_session, roomy_id) == []
    assert flags_on(db_session, breakout_id) == []
    assert _venue_staff_notices() == []


def test_one_change_gives_each_booking_only_its_own_reasons_in_order(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    """ADR-0094 decision 6: timing, venue requirements, then attendance."""
    _approve_change(
        db_session,
        event,
        {"expected_attendance": 150, "venue_requirements": "A stage", "start_time": "10:00"},
    )

    assert flags_on(db_session, main_id) == [TIMING_FLAG, REQUIREMENTS_FLAG, CAPACITY_FLAG]
    assert flags_on(db_session, breakout_id) == [TIMING_FLAG, REQUIREMENTS_FLAG]


def test_a_booking_still_asking_is_marked_and_one_turned_down_is_not(
    db_session: Session, auditorium: Venue, breakout_room: Venue, event: EventRequest
) -> None:
    """ADR-0094 decision 2: only a booking holding or asking for its venue is marked."""
    pending = raise_booking(auditorium, event, db_session)
    turned_down = raise_booking(
        breakout_room, event, db_session, expected_occupancy=30, **SECOND_PERIOD
    )
    decide(turned_down.id, "rejected", db_session, reason="Closed that day.")

    _approve_change(db_session, event, MOVE_START)

    assert flags_on(db_session, pending.id) == [TIMING_FLAG]
    assert flags_on(db_session, turned_down.id) == []


# --------------------------------------------------------------------------
# AC3 — the event can't go on while a booking is marked; Venue Staff resolve it
# --------------------------------------------------------------------------


def test_the_event_cant_be_confirmed_while_a_booking_is_marked(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    passed_safety_check: Callable[..., None],
) -> None:
    """Set back to Safety Review with an approval, so only the mark can refuse it."""
    _approve_change(db_session, event, {"expected_attendance": 150})
    passed_safety_check(EventRequestStatus.SAFETY_REVIEW)

    with pytest.raises(event_services.EventConfirmationNotAllowedError) as refusal:
        event_services.confirm_event_request(COORDINATOR_ID, event.reference, session=db_session)

    assert refusal.value.details == {
        "venue_arrangements": [
            f"Venue arrangement {main_id} is flagged (no longer suitable): {CAPACITY_REASON}"
        ]
    }


def test_the_event_cant_go_to_safety_review_while_a_booking_is_marked(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    _approve_change(db_session, event, MOVE_START)

    with pytest.raises(event_services.SafetyReviewNotAllowedError) as refusal:
        event_services.submit_for_safety_review(COORDINATOR_ID, event.reference, session=db_session)

    assert refusal.value.details == {
        "venue_arrangements": [
            f"Venue arrangement {main_id} is flagged (requires reconfirmation): {TIMING_REASON}"
        ]
    }


def test_venue_staff_reconfirming_the_booking_lets_the_event_go_on(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    _approve_change(db_session, event, MOVE_START)

    _reconfirm_as_listed(db_session, main_id)
    event_services.submit_for_safety_review(COORDINATOR_ID, event.reference, session=db_session)

    assert flags_on(db_session, main_id) == []
    assert reload_event(db_session, event.id).status is EventRequestStatus.SAFETY_REVIEW


def test_venue_staff_are_offered_the_period_and_occupancy_the_approved_change_implies(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    """SCRUM-59 reads the move from the history, so the change must be written there."""
    before = reload_request(db_session, main_id)
    starts_before, ends_before = before.starts_at, before.ends_at

    _approve_change(db_session, event, {"proposed_date": "2026-11-08", "expected_attendance": 90})

    [flagged] = venue_services.list_flagged_bookings(session=db_session)
    assert flagged.reconfirm_with.starts_at == starts_before + timedelta(days=7)
    assert flagged.reconfirm_with.ends_at == ends_before + timedelta(days=7)
    assert flagged.reconfirm_with.expected_occupancy == 90
    assert flagged.reconfirm_with.period_adjustable is True


# --------------------------------------------------------------------------
# AC4 — a change to anything else leaves every booking untouched
# --------------------------------------------------------------------------


@pytest.mark.parametrize("change", OTHER_CHANGES)
def test_a_change_to_anything_else_leaves_every_booking_untouched(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    breakout_id: int,
    change: dict[str, Any],
) -> None:
    _approve_change(db_session, event, change)

    assert flags_on(db_session, main_id) == []
    assert flags_on(db_session, breakout_id) == []
    assert _venue_staff_notices() == []


# --------------------------------------------------------------------------
# AC6 — a significant change withdraws a safety approval
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("change", "significant_fields"), SIGNIFICANT_CHANGES)
def test_a_significant_change_withdraws_the_safety_approval_naming_the_fields(
    db_session: Session,
    event: EventRequest,
    passed_safety_check: Callable[..., None],
    change: dict[str, Any],
    significant_fields: list[str],
) -> None:
    passed_safety_check(EventRequestStatus.APPROVED)

    _approve_change(db_session, event, change)

    assert _has_approval(db_session, event) is False
    assert _withdrawals(db_session, event) == [
        (COORDINATOR_ID, {"significant_fields": significant_fields})
    ]


def test_a_change_that_isnt_significant_keeps_the_safety_approval(
    db_session: Session, event: EventRequest, passed_safety_check: Callable[..., None]
) -> None:
    passed_safety_check(EventRequestStatus.APPROVED)

    _approve_change(db_session, event, NOT_SIGNIFICANT)

    assert _has_approval(db_session, event) is True
    assert _withdrawals(db_session, event) == []


def test_only_the_significant_fields_of_a_mixed_change_are_named(
    db_session: Session, event: EventRequest, passed_safety_check: Callable[..., None]
) -> None:
    passed_safety_check(EventRequestStatus.APPROVED)

    _approve_change(db_session, event, {**NOT_SIGNIFICANT, **MOVE_START})

    assert _withdrawals(db_session, event) == [
        (COORDINATOR_ID, {"significant_fields": ["start_time"]})
    ]


def test_an_event_without_a_safety_approval_has_nothing_withdrawn(
    db_session: Session, event: EventRequest
) -> None:
    _approve_change(db_session, event, MOVE_START)

    assert _withdrawals(db_session, event) == []


# --------------------------------------------------------------------------
# AC7 — a Confirmed event returns to Approved after any significant change
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("change", "significant_fields"), SIGNIFICANT_CHANGES)
def test_a_confirmed_event_returns_to_approved_after_any_significant_change(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    passed_safety_check: Callable[..., None],
    change: dict[str, Any],
    significant_fields: list[str],
) -> None:
    """Not only a date or time change: a fall in attendance flags nothing, yet does."""
    passed_safety_check(EventRequestStatus.CONFIRMED)

    _approve_change(db_session, event, change)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED
    assert _withdrawals(db_session, event) == [
        (COORDINATOR_ID, {"significant_fields": significant_fields})
    ]


def test_a_confirmed_event_stays_confirmed_after_a_change_that_isnt_significant(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    passed_safety_check: Callable[..., None],
) -> None:
    passed_safety_check(EventRequestStatus.CONFIRMED)

    _approve_change(db_session, event, NOT_SIGNIFICANT)

    assert reload_event(db_session, event.id).status is EventRequestStatus.CONFIRMED
    assert _has_approval(db_session, event) is True
    assert flags_on(db_session, main_id) == []


def test_the_return_to_approved_is_committed_even_when_every_notice_fails(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    passed_safety_check: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The notices commit too, so with them gone only the decision's commit is left."""
    passed_safety_check(EventRequestStatus.CONFIRMED)
    _lose_every_notice(monkeypatch)

    _approve_change(db_session, event, MOVE_START)
    db_session.rollback()

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED
    assert _has_approval(db_session, event) is False
    assert flags_on(db_session, main_id) == [TIMING_FLAG]


def test_a_returned_event_must_pass_a_new_safety_check_to_be_confirmed_again(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    passed_safety_check: Callable[..., None],
) -> None:
    passed_safety_check(EventRequestStatus.CONFIRMED)
    _approve_change(db_session, event, {"expected_attendance": 60})

    event_services.submit_for_safety_review(COORDINATOR_ID, event.reference, session=db_session)
    with pytest.raises(event_services.EventConfirmationNotAllowedError) as refusal:
        event_services.confirm_event_request(COORDINATOR_ID, event.reference, session=db_session)

    assert refusal.value.details is not None
    assert list(refusal.value.details) == ["safety_check"]


# --------------------------------------------------------------------------
# SCRUM-33 AC9, as after a direct edit — a change made in Safety Review
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "detail", "status_after"),
    [
        pytest.param(
            MOVE_START,
            f"Changed: start time. {BACK_IN_PLANNING}",
            EventRequestStatus.APPROVED,
            id="a-mark-sends-it-back",
        ),
        pytest.param(
            {"expected_attendance": 60},
            "Changed: expected attendance.",
            EventRequestStatus.SAFETY_REVIEW,
            id="no-mark-keeps-it-there",
        ),
    ],
)
def test_the_safety_officer_is_told_of_a_change_approved_in_safety_review(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    safety_officer: User,
    change: dict[str, Any],
    detail: str,
    status_after: EventRequestStatus,
) -> None:
    event.status = EventRequestStatus.SAFETY_REVIEW
    db_session.commit()

    _approve_change(db_session, event, change)

    assert _notices_to(SAFETY_OFFICER_ID, NotificationKind.SAFETY_REVIEW_EVENT_CHANGED) == [
        (event.id, detail)
    ]
    assert reload_event(db_session, event.id).status is status_after


@pytest.mark.parametrize(
    ("status", "change"),
    [
        pytest.param(EventRequestStatus.APPROVED, MOVE_START, id="not-in-safety-review"),
        pytest.param(EventRequestStatus.SAFETY_REVIEW, NOT_SIGNIFICANT, id="not-significant"),
    ],
)
def test_the_safety_officer_is_not_told_of_any_other_approved_change(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    safety_officer: User,
    status: EventRequestStatus,
    change: dict[str, Any],
) -> None:
    event.status = status
    db_session.commit()

    _approve_change(db_session, event, change)

    assert _notices_to(SAFETY_OFFICER_ID, NotificationKind.SAFETY_REVIEW_EVENT_CHANGED) == []


# --------------------------------------------------------------------------
# A change that isn't applied reassesses nothing
# --------------------------------------------------------------------------


def test_a_rejected_change_marks_nothing_and_keeps_the_safety_approval(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    passed_safety_check: Callable[..., None],
) -> None:
    passed_safety_check(EventRequestStatus.CONFIRMED)
    change_request_id = _raise_change(db_session, event, MOVE_START)

    _decide_change(db_session, event, change_request_id, REJECT)

    assert flags_on(db_session, main_id) == []
    assert _venue_staff_notices() == []
    assert reload_event(db_session, event.id).status is EventRequestStatus.CONFIRMED
    assert _has_approval(db_session, event) is True


def test_a_refused_stale_approval_marks_nothing(
    db_session: Session,
    event: EventRequest,
    main_id: int,
    passed_safety_check: Callable[..., None],
) -> None:
    change_request_id = _raise_change(db_session, event, {"expected_attendance": 150})
    edit_event(db_session, event, {"expected_attendance": 70})
    passed_safety_check(EventRequestStatus.SAFETY_REVIEW)

    with pytest.raises(AppError):
        _decide_change(db_session, event, change_request_id, {"outcome": "approved"})
    db_session.rollback()

    assert flags_on(db_session, main_id) == []
    assert _has_approval(db_session, event) is True
    assert reload_event(db_session, event.id).status is EventRequestStatus.SAFETY_REVIEW
