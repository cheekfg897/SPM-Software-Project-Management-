"""Unit tests for SCRUM-99: the Safety Officer names what to rework, when not approving.

AC2: recording Reject or Request Changes, the Safety Officer may name venue arrangements
and equipment lines. Each named arrangement is flagged for Venue Staff to reconfirm, as
a change flags it (SCRUM-58, ADR-0094), with "Flagged by the Safety Officer: <reason>";
each named line is reopened as a quantity change reopens it (SCRUM-37 AC4), so Technical
Support record a fresh outcome. Nothing else is touched. AC3 (delivered by SCRUM-98):
naming nothing flags nothing. AC4: the outcome on the event's record says what was
named. AC5: a flag clears when Venue Staff reconfirm or reject the arrangement
(SCRUM-59); a line when Technical Support record its outcome. AC6: resubmission is
refused while any of them is open. AC7: Venue Staff are told of each flagged
arrangement, Technical Support of each reopened line (ADR-0113).

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, assigned to Event Coordinator 3, on 15 October 2026 from 09:00 to
17:00), put in Safety Review with two approved arrangements and two fulfilled lines.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment.models import EquipmentReservation, EquipmentType
from app.modules.events import routes
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    CoordinatorEventRecord,
    SafetyOutcomeAsShown,
    SafetyReviewNotAllowedError,
    get_event_record_for_coordinator,
    list_events_awaiting_safety_review,
    record_equipment_outcome,
    record_safety_outcome,
    submit_for_safety_review,
)
from app.modules.notifications.services import NotificationKind, list_notifications_for_recipient
from app.modules.venue import services as venue_services
from app.modules.venue.models import BookingRequestStatus, Venue, VenueBookingRequest
from tests.events.cases import AddLine

pytestmark = pytest.mark.scrum_99

REFERENCE = "EVR-AAAAAAAA"
COORDINATOR_ID = 3
VENUE_STAFF_ID = 4
#: The two Technical Support Staff ``saved_users`` saves.
TECHNICAL_SUPPORT_IDS = [5, 2]
SAFETY_OFFICER_ID = 20
REASON = "The fire exit on the east side is blocked by the stage."
FLAG_REASON = f"Flagged by the Safety Officer: {REASON}"
CHECKLIST = {
    "attendance_vs_capacity": "80 expected in a hall for 100.",
    "venue_layout": "Theatre layout, aisles clear.",
    "emergency_access": "East exit blocked.",
    "accessibility": "Step-free entrance confirmed.",
    "equipment_placement": "Projector cables across the aisle.",
    "crowd_movement": "One-way flow at the doors.",
    "venue_restrictions": "No open flames.",
}
NOT_APPROVED_OUTCOMES = ["rejected", "changes_requested"]
ReloadEventRequest = Callable[[int], EventRequest]


def _record(session: Session, outcome: str, **named: Any) -> EventRequest:
    """Record ``outcome`` with the checklist and reason, naming what ``named`` says."""
    payload = {"outcome": outcome, "checklist": CHECKLIST, "reason": REASON, **named}
    return record_safety_outcome(SAFETY_OFFICER_ID, REFERENCE, payload, session=session)


def _field_errors(session: Session, outcome: str, **named: Any) -> dict[str, Any]:
    with pytest.raises(ValidationError) as exc_info:
        _record(session, outcome, **named)
    return exc_info.value.details


def _flags(session: Session, arrangement_id: int) -> list[tuple[str, str]]:
    session.expire_all()
    arrangement = session.get(VenueBookingRequest, arrangement_id)
    assert arrangement is not None
    return [(flag.kind.value, flag.reason) for flag in arrangement.reassessment_flags]


def _line(session: Session, line_id: int) -> EventEquipmentLine:
    session.expire_all()
    line = session.get(EventEquipmentLine, line_id)
    assert line is not None
    return line


def _significant_change_notices(user_id: int) -> list[str | None]:
    rows = []
    for notification in list_notifications_for_recipient(user_id):
        if notification.kind is NotificationKind.SIGNIFICANT_CHANGE:
            rows.append(notification.detail)
    return rows


@pytest.fixture()
def in_review(
    saved_users: list[User],
    saved_event_request: EventRequest,
    make_user: Callable[..., User],
    save: Callable[..., None],
) -> EventRequest:
    """``saved_event_request`` in Safety Review, with a Safety Officer saved."""
    officer = make_user(
        email="safety@example.com", role=Role.SAFETY_OFFICER, user_id=SAFETY_OFFICER_ID
    )
    saved_event_request.status = EventRequestStatus.SAFETY_REVIEW
    save(officer, saved_event_request)
    return saved_event_request


def _approved_arrangement(
    event: EventRequest, venue: Venue, hour: int, save: Callable[..., None]
) -> VenueBookingRequest:
    """An approved arrangement at ``venue`` on the event's day, for an hour."""
    arrangement = VenueBookingRequest(
        event_id=event.id,
        venue_id=venue.id,
        # 15 October 2026 in Singapore (UTC+8), inside the event and the venue's hours.
        starts_at=datetime(2026, 10, 15, hour - 8, tzinfo=UTC),
        ends_at=datetime(2026, 10, 15, hour - 7, tzinfo=UTC),
        purpose="Main session",
        expected_occupancy=80,
        status=BookingRequestStatus.APPROVED,
        requested_by=COORDINATOR_ID,
    )
    save(arrangement)
    return arrangement


@pytest.fixture()
def hall(in_review: EventRequest, venue: Venue, save: Callable[..., None]) -> VenueBookingRequest:
    """The event's approved arrangement at Main Hall, 09:00-10:00."""
    return _approved_arrangement(in_review, venue, 9, save)


@pytest.fixture()
def annex(
    in_review: EventRequest,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
) -> VenueBookingRequest:
    """The event's approved arrangement at the Annex, 11:00-12:00."""
    annex_venue = make_venue(name="Annex")
    save(annex_venue)
    return _approved_arrangement(in_review, annex_venue, 11, save)


@pytest.fixture()
def lines(in_review: EventRequest, add_line: AddLine) -> list[EventEquipmentLine]:
    """Two equipment lines Technical Support fulfilled, 2 units each."""
    return [add_line(2), add_line(2)]


# --------------------------------------------------------------------------
# AC2 — named arrangements are flagged, named lines reopened, nothing else
# --------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", NOT_APPROVED_OUTCOMES)
def test_a_named_arrangement_is_flagged_with_the_reason_and_the_others_are_left(
    db_session: Session,
    hall: VenueBookingRequest,
    annex: VenueBookingRequest,
    reload_event_request: ReloadEventRequest,
    outcome: str,
) -> None:
    _record(db_session, outcome, flagged_arrangement_ids=[hall.id])

    assert _flags(db_session, hall.id) == [("requires_reconfirmation", FLAG_REASON)]
    assert _flags(db_session, annex.id) == []
    assert reload_event_request(hall.event_id).status is EventRequestStatus.APPROVED


@pytest.mark.parametrize("outcome", NOT_APPROVED_OUTCOMES)
def test_a_named_line_is_reopened_and_the_others_are_left(
    db_session: Session, hall: VenueBookingRequest, lines: list[EventEquipmentLine], outcome: str
) -> None:
    named, other = lines

    _record(db_session, outcome, reopened_line_ids=[named.id])

    reopened = _line(db_session, named.id)
    assert reopened.status is EquipmentLineStatus.REQUESTED
    assert reopened.provided_quantity is None
    assert _line(db_session, other.id).status is EquipmentLineStatus.FULFILLED
    assert _line(db_session, other.id).provided_quantity == 2


@pytest.mark.scrum_60
def test_a_named_lines_reservations_are_marked_for_reassessment(
    db_session: Session, lines: list[EventEquipmentLine], save: Callable[..., None]
) -> None:
    """As a new quantity marks them (SCRUM-60 AC8), so the fresh outcome settles them.

    The other line's reservation is left unmarked (ADR-0113 decision 4).
    """
    named, other = lines
    for line in lines:
        save(
            EquipmentReservation(
                event_id=line.event_request_id,
                equipment_type_id=line.equipment_type_id,
                quantity=2,
                starts_at=datetime(2026, 10, 15, 1, tzinfo=UTC),
                ends_at=datetime(2026, 10, 15, 9, tzinfo=UTC),
                reserved_by=TECHNICAL_SUPPORT_IDS[0],
            )
        )

    _record(db_session, "changes_requested", reopened_line_ids=[named.id])

    db_session.expire_all()
    marked = {}
    for reservation in db_session.scalars(select(EquipmentReservation)):
        marked[reservation.equipment_type_id] = reservation.needs_reassessment
    assert marked == {named.equipment_type_id: True, other.equipment_type_id: False}


def test_naming_an_arrangement_twice_flags_it_once(
    db_session: Session, hall: VenueBookingRequest
) -> None:
    _record(db_session, "rejected", flagged_arrangement_ids=[hall.id, hall.id])

    assert _flags(db_session, hall.id) == [("requires_reconfirmation", FLAG_REASON)]


def test_naming_a_line_twice_reopens_and_tells_about_it_once(
    db_session: Session, hall: VenueBookingRequest, lines: list[EventEquipmentLine]
) -> None:
    _record(db_session, "rejected", reopened_line_ids=[lines[0].id, lines[0].id])

    assert _significant_change_notices(TECHNICAL_SUPPORT_IDS[0]) == [
        f"Equipment line {lines[0].id} (Item 0, 2 requested) reopened: {FLAG_REASON}"
    ]


def test_naming_nothing_flags_nothing_and_the_event_still_returns_to_planning(
    db_session: Session,
    hall: VenueBookingRequest,
    lines: list[EventEquipmentLine],
    reload_event_request: ReloadEventRequest,
) -> None:
    """AC3, delivered by SCRUM-98: kept here to show naming is optional."""
    _record(db_session, "rejected")

    assert _flags(db_session, hall.id) == []
    assert _line(db_session, lines[0].id).status is EquipmentLineStatus.FULFILLED
    assert reload_event_request(hall.event_id).status is EventRequestStatus.APPROVED


def test_the_history_entry_keeps_what_was_named(
    db_session: Session,
    hall: VenueBookingRequest,
    lines: list[EventEquipmentLine],
    history_of: Callable[[int], list[tuple[EventHistoryKind, int | None, Any]]],
) -> None:
    _record(
        db_session,
        "changes_requested",
        flagged_arrangement_ids=[hall.id],
        reopened_line_ids=[lines[1].id],
    )

    kind, actor_id, details = history_of(hall.event_id)[-1]
    assert (kind, actor_id) == (EventHistoryKind.SAFETY_OUTCOME_RECORDED, SAFETY_OFFICER_ID)
    assert details["flagged_arrangement_ids"] == [hall.id]
    assert details["reopened_line_ids"] == [lines[1].id]


@pytest.mark.parametrize("field", ["flagged_arrangement_ids", "reopened_line_ids"])
def test_an_approval_names_nothing(
    db_session: Session,
    hall: VenueBookingRequest,
    lines: list[EventEquipmentLine],
    reload_event_request: ReloadEventRequest,
    field: str,
) -> None:
    named_id = hall.id if field == "flagged_arrangement_ids" else lines[0].id

    errors = _field_errors(db_session, "approved", **{field: [named_id]})

    assert errors == {field: ["Only a rejection or a request for changes can name what to rework."]}
    assert reload_event_request(hall.event_id).status is EventRequestStatus.SAFETY_REVIEW


@pytest.mark.parametrize(
    ("status"),
    [status for status in BookingRequestStatus if status is not BookingRequestStatus.APPROVED],
    ids=lambda status: status.value,
)
def test_only_an_approved_arrangement_of_the_event_can_be_named(
    db_session: Session,
    hall: VenueBookingRequest,
    annex: VenueBookingRequest,
    save: Callable[..., None],
    reload_event_request: ReloadEventRequest,
    status: BookingRequestStatus,
) -> None:
    """In Safety Review every live arrangement is approved (SCRUM-97), so only those."""
    annex.status = status
    save(annex)

    errors = _field_errors(db_session, "rejected", flagged_arrangement_ids=[hall.id, annex.id])

    assert errors == {
        "flagged_arrangement_ids": [
            f"Venue arrangement {annex.id} is not one of this event's approved arrangements."
        ]
    }
    assert _flags(db_session, hall.id) == []
    assert reload_event_request(hall.event_id).status is EventRequestStatus.SAFETY_REVIEW


def test_an_unknown_arrangement_or_another_events_is_refused(
    db_session: Session,
    hall: VenueBookingRequest,
    make_event_request: Callable[..., EventRequest],
    venue: Venue,
    save: Callable[..., None],
) -> None:
    other_event = make_event_request(reference="EVR-OTHER001", coordinator_id=COORDINATOR_ID)
    save(other_event)
    elsewhere = _approved_arrangement(other_event, venue, 13, save)

    errors = _field_errors(db_session, "rejected", flagged_arrangement_ids=[elsewhere.id, 9999])

    assert errors == {
        "flagged_arrangement_ids": [
            f"Venue arrangement {elsewhere.id} is not one of this event's approved arrangements.",
            "Venue arrangement 9999 is not one of this event's approved arrangements.",
        ]
    }


def test_an_unknown_line_or_another_events_is_refused_and_nothing_changes(
    db_session: Session,
    hall: VenueBookingRequest,
    lines: list[EventEquipmentLine],
    make_event_request: Callable[..., EventRequest],
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
    reload_event_request: ReloadEventRequest,
) -> None:
    other_event = make_event_request(reference="EVR-OTHER001", coordinator_id=COORDINATOR_ID)
    save(other_event)
    elsewhere_type = db_session.get(EquipmentType, lines[0].equipment_type_id)
    elsewhere = make_equipment_line(other_event, elsewhere_type)
    save(elsewhere)

    errors = _field_errors(
        db_session,
        "rejected",
        flagged_arrangement_ids=[hall.id],
        reopened_line_ids=[lines[0].id, elsewhere.id, 9999],
    )

    assert errors == {
        "reopened_line_ids": [
            f"Equipment line {elsewhere.id} is not one of this event's lines.",
            "Equipment line 9999 is not one of this event's lines.",
        ]
    }
    assert _flags(db_session, hall.id) == []
    assert _line(db_session, lines[0].id).status is EquipmentLineStatus.FULFILLED
    assert reload_event_request(hall.event_id).status is EventRequestStatus.SAFETY_REVIEW


@pytest.mark.parametrize(
    ("value", "messages"),
    [
        ("1", ["Not a valid list."]),
        (None, ["Field may not be null."]),
        (["a"], {0: ["Not a valid integer."]}),
        ([True], {0: ["Not a valid integer."]}),
        ([0], {0: ["flagged_arrangement_ids must be a positive number."]}),
    ],
    ids=["text", "null", "text-id", "boolean-id", "zero"],
)
def test_the_named_ids_must_be_a_list_of_positive_whole_numbers(
    db_session: Session, hall: VenueBookingRequest, value: Any, messages: Any
) -> None:
    errors = _field_errors(db_session, "rejected", flagged_arrangement_ids=value)

    assert errors == {"flagged_arrangement_ids": messages}


# --------------------------------------------------------------------------
# AC4 — the outcome on the event's record says what was named
# --------------------------------------------------------------------------


def test_the_coordinators_record_shows_the_outcome_and_how_much_was_named(
    db_session: Session, hall: VenueBookingRequest, lines: list[EventEquipmentLine]
) -> None:
    _record(
        db_session,
        "changes_requested",
        flagged_arrangement_ids=[hall.id],
        reopened_line_ids=[lines[0].id, lines[1].id],
    )

    record = get_event_record_for_coordinator(COORDINATOR_ID, REFERENCE, session=db_session)

    assert record.safety_outcome is not None
    assert record.safety_outcome.outcome == "changes_requested"
    assert record.safety_outcome.reason == REASON
    assert record.safety_outcome.flagged_arrangement_count == 1
    assert record.safety_outcome.reopened_line_count == 2
    reasons = [flag.reason for flag in record.venue_arrangements[0].reassessment_flags]
    assert reasons == [FLAG_REASON]


def test_the_coordinators_record_route_sends_the_safety_outcome(
    call_route: Callable[..., Any],
    replace_services: Callable[..., Any],
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    make_event_request: Callable[..., EventRequest],
) -> None:
    outcome = SafetyOutcomeAsShown(
        outcome="rejected",
        checklist=CHECKLIST,
        reason=REASON,
        recorded_by="Sam Safety",
        recorded_at=datetime(2026, 10, 2, 2, tzinfo=UTC),
        flagged_arrangement_count=1,
        reopened_line_count=2,
    )
    record = CoordinatorEventRecord(
        event_request=make_event_request(status=EventRequestStatus.APPROVED),
        coordinator=None,
        safety_outcome=outcome,
    )
    replace_services(routes, {"get_event_record_for_coordinator": record})
    coordinator = make_user(role=Role.EVENT_COORDINATOR, user_id=COORDINATOR_ID)

    response, status = call_route(
        "events.get_my_request",
        "GET",
        f"/api/events/requests/{REFERENCE}",
        {"reference": REFERENCE},
        token_for(coordinator),
    )

    assert status == 200
    assert response.get_json()["safety_outcome"] == {
        "outcome": "rejected",
        "checklist": CHECKLIST,
        "reason": REASON,
        "recorded_by": "Sam Safety",
        "recorded_at": "2026-10-02T10:00:00+08:00",
        "flagged_arrangement_count": 1,
        "reopened_line_count": 2,
    }


def test_an_outcome_that_named_nothing_counts_none(
    db_session: Session, hall: VenueBookingRequest
) -> None:
    _record(db_session, "rejected")

    record = get_event_record_for_coordinator(COORDINATOR_ID, REFERENCE, session=db_session)

    assert record.safety_outcome is not None
    assert record.safety_outcome.flagged_arrangement_count == 0
    assert record.safety_outcome.reopened_line_count == 0


def test_the_coordinators_record_has_no_outcome_before_one_is_recorded(
    db_session: Session, hall: VenueBookingRequest
) -> None:
    record = get_event_record_for_coordinator(COORDINATOR_ID, REFERENCE, session=db_session)

    assert record.safety_outcome is None


@pytest.fixture()
def unused_venue_and_type(
    make_venue: Callable[..., Venue],
    make_equipment_type: Callable[..., EquipmentType],
    save: Callable[..., None],
) -> None:
    """Save a venue and an equipment type nothing uses, ahead of the ones booked.

    The booked venues and types then get higher ids than the arrangements and lines that
    use them, so an id taken from the wrong row can't equal the right one.
    """
    save(make_venue(name="Unused"), make_equipment_type(name="Unused"))


def test_the_safety_officers_list_gives_each_arrangement_and_line_its_id(
    db_session: Session,
    unused_venue_and_type: None,
    hall: VenueBookingRequest,
    annex: VenueBookingRequest,
    lines: list[EventEquipmentLine],
) -> None:
    """The ids the Safety Officer names (AC2) are the arrangement's and line's own."""
    assert [hall.id, annex.id] != [hall.venue_id, annex.venue_id]
    assert [line.id for line in lines] != [line.equipment_type_id for line in lines]

    (awaiting,) = list_events_awaiting_safety_review(session=db_session)

    assert [venue.id for venue in awaiting.venues] == [hall.id, annex.id]
    assert [line.id for line in awaiting.equipment] == [lines[0].id, lines[1].id]


# --------------------------------------------------------------------------
# AC5, AC6 — the flags clear as each is settled, and only then can it go back
# --------------------------------------------------------------------------


def test_resubmission_waits_for_each_flag_and_line_to_be_settled(
    db_session: Session, hall: VenueBookingRequest, lines: list[EventEquipmentLine]
) -> None:
    _record(
        db_session,
        "changes_requested",
        flagged_arrangement_ids=[hall.id],
        reopened_line_ids=[lines[0].id],
    )
    with pytest.raises(SafetyReviewNotAllowedError) as exc_info:
        submit_for_safety_review(COORDINATOR_ID, REFERENCE, session=db_session)
    assert exc_info.value.details == {
        "venue_arrangements": [
            f"Venue arrangement {hall.id} is flagged (requires reconfirmation): {FLAG_REASON}"
        ],
        "equipment": [f"Equipment request {lines[0].id} has no outcome from Technical Support."],
    }

    venue_services.reconfirm_flagged_booking(
        hall.id,
        {"starts_at": "2026-10-15T09:00:00+08:00", "ends_at": "2026-10-15T10:00:00+08:00"},
        reconfirmed_by=VENUE_STAFF_ID,
        session=db_session,
    )
    record_equipment_outcome(
        TECHNICAL_SUPPORT_IDS[0],
        REFERENCE,
        lines[0].id,
        {"provided_quantity": 2},
        session=db_session,
    )
    resubmitted = submit_for_safety_review(COORDINATOR_ID, REFERENCE, session=db_session)

    assert resubmitted.status is EventRequestStatus.SAFETY_REVIEW


def test_rejecting_a_flagged_arrangement_settles_its_flag(
    db_session: Session, hall: VenueBookingRequest
) -> None:
    _record(db_session, "rejected", flagged_arrangement_ids=[hall.id])

    venue_services.reject_flagged_booking(
        hall.id,
        {"reason": "Hall can't be cleared."},
        rejected_by=VENUE_STAFF_ID,
        session=db_session,
    )

    flagged = venue_services.list_arrangements_flagged_after_change(
        hall.event_id, session=db_session
    )
    assert flagged == []


def test_a_flag_the_safety_officer_left_appears_in_venue_staffs_queue_unmoved(
    db_session: Session, hall: VenueBookingRequest
) -> None:
    """SCRUM-59 AC1, AC2: nothing moved the event, so the period stays."""
    _record(db_session, "rejected", flagged_arrangement_ids=[hall.id])

    (flagged,) = venue_services.list_flagged_bookings(session=db_session)

    assert flagged.shown.request.id == hall.id
    assert flagged.reconfirm_with.starts_at == datetime(2026, 10, 15, 1, tzinfo=UTC)


# --------------------------------------------------------------------------
# AC7 — Venue Staff and Technical Support are told of what was named
# --------------------------------------------------------------------------


def test_venue_staff_are_told_of_each_flagged_arrangement(
    db_session: Session, hall: VenueBookingRequest, annex: VenueBookingRequest
) -> None:
    _record(db_session, "rejected", flagged_arrangement_ids=[annex.id, hall.id])

    # Newest first: told in the order named, the annex first.
    assert _significant_change_notices(VENUE_STAFF_ID) == [
        f"Venue arrangement {hall.id} at Main Hall: {FLAG_REASON}",
        f"Venue arrangement {annex.id} at Annex: {FLAG_REASON}",
    ]


def test_technical_support_are_told_of_each_reopened_line(
    db_session: Session, hall: VenueBookingRequest, lines: list[EventEquipmentLine]
) -> None:
    _record(db_session, "changes_requested", reopened_line_ids=[lines[0].id, lines[1].id])

    for user_id in TECHNICAL_SUPPORT_IDS:
        assert sorted(_significant_change_notices(user_id)) == [
            f"Equipment line {lines[0].id} (Item 0, 2 requested) reopened: {FLAG_REASON}",
            f"Equipment line {lines[1].id} (Item 1, 2 requested) reopened: {FLAG_REASON}",
        ]


def test_nobody_else_is_told_when_nothing_is_named(
    db_session: Session, hall: VenueBookingRequest, lines: list[EventEquipmentLine]
) -> None:
    _record(db_session, "rejected")

    assert _significant_change_notices(VENUE_STAFF_ID) == []
    assert _significant_change_notices(TECHNICAL_SUPPORT_IDS[0]) == []
