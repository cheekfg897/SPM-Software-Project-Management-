"""Unit tests for SCRUM-24 AC10 — the Event Organiser sees everything on their record.

Product Owner decision of 25 Oct: the organiser opens any submitted event of their
client organisation and sees everything on its record, read-only, at every stage, not
only once it is Confirmed (SCRUM-24 AC10, SCRUM-49 AC13): every venue arrangement with
its status, holds with their expiry and flags with their reason; the equipment lines
with their technical notes, outcome, note, quantities and reviewer (SCRUM-37 AC5,
SCRUM-48 AC5); the Operational Safety Check's outcome with its date, checklist and
comments; the preparation details (SCRUM-84 AC2, SCRUM-85 AC2); and the planning notes
(SCRUM-33 AC1). When a Confirmed event returns to Approved, nothing is hidden. The
record is the staff record's sections (ADR-0095) beside the organiser's own (ADR-0104,
which supersedes ADR-0098's and ADR-0099's hiding rules). The equipment lines are
tested in ``test_organiser_equipment_view.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment.models import EquipmentReservation, EquipmentType, PreparationStatus
from app.modules.equipment.services import ReservationAsShown
from app.modules.events import routes
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import (
    EventRecord,
    OrganiserEventRecord,
    SafetyOutcomeAsShown,
    get_event_record_for_organiser,
    withdraw_safety_approval,
)
from app.modules.venue.models import (
    BookingRequestStatus,
    PreparationStatus as VenuePreparationStatus,
    ReassessmentFlagKind,
    UnavailabilityCategory,
    Venue,
)
from app.modules.venue.services import ReassessmentForRecord, UnavailabilityForRecord
from tests.conftest import HOLD_STATUSES, place_hold_on
from tests.events.cases import AddLine, Arrange, SaveArrangement, arrangement_for_record

pytestmark = [pytest.mark.scrum_24, pytest.mark.scrum_49]

ORGANISER_ID = 7
COORDINATOR_ID = 3
TECHNICAL_SUPPORT_ID = 5
SAFETY_OFFICER_ID = 11
REFERENCE = "EVR-AAAAAAAA"
#: Every status the event can be in, built from the enum so a new status is checked too.
EVERY_STATUS = list(EventRequestStatus)
CHECKLIST = {
    "attendance_vs_capacity": "250 expected; the hall holds 300.",
    "emergency_access": "Both fire exits kept clear.",
}
APPROVED_AT = datetime(2026, 10, 23, 4, 30, tzinfo=UTC)
WITHDRAWN_AT = datetime(2026, 10, 24, 1, 0, tzinfo=UTC)
RESERVED_FROM = datetime(2026, 11, 1, 1, 0, tzinfo=UTC)
RESERVED_TO = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
#: Every key the organiser's record sends: the request with both notes, the sections
#: every record shows, and the staff record's sections (ADR-0104).
RECORD_KEYS = {
    "reference",
    "status",
    "name",
    "purpose",
    "description",
    "proposed_date",
    "end_date",
    "start_time",
    "end_time",
    "expected_attendance",
    "venue_requirements",
    "accessibility_needs",
    "equipment_requirements",
    "registration_required",
    "created_at",
    "programme_notes",
    "internal_planning_notes",
    "coordinator",
    "decision",
    "clarifications",
    "venue_arrangements",
    "equipment_lines",
    "equipment_reservations",
    "safety_outcome",
}


RecordEntry = Callable[..., None]


@pytest.fixture()
def safety_officer(make_user: Callable[..., User], save: Callable[..., None]) -> User:
    """Safety Officer 11, saved, so the outcome can name who recorded it."""
    officer = make_user(
        email="safety11@example.com",
        full_name="Sam Safety",
        role=Role.SAFETY_OFFICER,
        user_id=SAFETY_OFFICER_ID,
    )
    save(officer)
    return officer


@pytest.fixture()
def safety_approved(record_entry: RecordEntry, safety_officer: User) -> None:
    """The Safety Officer approves ``saved_event_request`` on 23 Oct, with comments."""
    record_entry(
        EventHistoryKind.SAFETY_OUTCOME_RECORDED,
        APPROVED_AT,
        actor_id=SAFETY_OFFICER_ID,
        details={"outcome": "approved", "checklist": CHECKLIST, "reason": "Keep aisles clear."},
    )


@pytest.fixture()
def reserve(
    equipment_type: EquipmentType, save: Callable[..., None]
) -> Callable[[EventRequest], EquipmentReservation]:
    """Save four projectors for ``event``, reserved by user 5, half of them tested."""

    def _reserve(event: EventRequest) -> EquipmentReservation:
        reservation = EquipmentReservation(
            event_id=event.id,
            equipment_type_id=equipment_type.id,
            quantity=4,
            starts_at=RESERVED_FROM,
            ends_at=RESERVED_TO,
            reserved_by=TECHNICAL_SUPPORT_ID,
        )
        reservation.preparation_status = PreparationStatus.IN_PROGRESS
        reservation.preparation_notes = "Two of four tested."
        save(reservation)
        return reservation

    return _reserve


@pytest.fixture()
def another_event(
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
    venue: Venue,
    save_arrangement: SaveArrangement,
    reserve: Callable[[EventRequest], EquipmentReservation],
) -> EventRequest:
    """Another of the organiser's events, with a venue and a reservation of its own."""
    other_event = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=COORDINATOR_ID)
    save(other_event)
    save_arrangement(other_event, venue, BookingRequestStatus.APPROVED)
    reserve(other_event)
    return other_event


# --------------------------------------------------------------------------
# AC10 — at every stage, every arrangement, line, reservation and outcome
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", EVERY_STATUS, ids=lambda status: status.value)
def test_at_every_stage_the_organiser_sees_everything_on_the_record(
    db_session: Session,
    saved_users: list[User],
    set_status: Callable[[EventRequestStatus], None],
    arrange: Arrange,
    add_line: AddLine,
    saved_event_request: EventRequest,
    reserve: Callable[[EventRequest], EquipmentReservation],
    safety_approved: None,
    status: EventRequestStatus,
) -> None:
    """Not only once Confirmed (SCRUM-49 AC13): nothing waits on the event's status."""
    arrange(BookingRequestStatus.APPROVED)
    arrange(BookingRequestStatus.PENDING)
    add_line(2)
    reserve(saved_event_request)
    set_status(status)

    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE, session=db_session)

    statuses = [arrangement.status for arrangement in record.venue_arrangements]
    assert statuses == [BookingRequestStatus.APPROVED, BookingRequestStatus.PENDING]
    assert [line.equipment_type_name for line in record.equipment_lines] == ["Item 0"]
    assert [reserved.quantity for reserved in record.equipment_reservations] == [4]
    assert record.safety_outcome is not None
    assert record.safety_outcome.outcome == "approved"


def test_every_arrangement_is_shown_whatever_its_status(
    db_session: Session,
    saved_users: list[User],
    arrange: Arrange,
    save: Callable[..., None],
) -> None:
    """Retired ones too: a withdrawn or released arrangement stays on the record."""
    for status in BookingRequestStatus:
        arrangement = arrange(status)
        if status in HOLD_STATUSES:
            place_hold_on(arrangement, datetime(2026, 10, 30, 9, 0, tzinfo=UTC), save)

    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE, session=db_session)

    statuses = [arrangement.status for arrangement in record.venue_arrangements]
    assert statuses == list(BookingRequestStatus)


def test_an_arrangement_shows_its_preparation_as_venue_staff_left_it(
    db_session: Session, saved_users: list[User], arrange: Arrange
) -> None:
    """SCRUM-84 AC2: the organiser sees the preparation details too."""
    arrangement = arrange(BookingRequestStatus.APPROVED)
    arrangement.preparation_status = VenuePreparationStatus.READY
    arrangement.preparation_notes = "Stage built."
    db_session.commit()

    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE, session=db_session)

    assert record.venue_arrangements == (
        arrangement_for_record(
            preparation_status=VenuePreparationStatus.READY, preparation_notes="Stage built."
        ),
    )


def test_the_organiser_sees_each_reservation_with_its_preparation_and_who_made_it(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    reserve: Callable[[EventRequest], EquipmentReservation],
) -> None:
    """SCRUM-85 AC2, and the names of the staff who acted (AC10)."""
    reservation = reserve(saved_event_request)

    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE, session=db_session)

    assert record.equipment_reservations == (
        ReservationAsShown(
            id=reservation.id,
            equipment_type_id=reservation.equipment_type_id,
            equipment_type_name="Projector",
            quantity=4,
            starts_at=RESERVED_FROM,
            ends_at=RESERVED_TO,
            reserved_by="Alice Example",
            created_at=reservation.created_at,
            needs_attention=False,
            preparation_status=PreparationStatus.IN_PROGRESS,
            preparation_notes="Two of four tested.",
        ),
    )


def test_the_organiser_sees_the_safety_check_with_its_checklist_and_comments(
    db_session: Session, saved_users: list[User], safety_approved: None
) -> None:
    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE, session=db_session)

    assert record.safety_outcome == SafetyOutcomeAsShown(
        outcome="approved",
        checklist=CHECKLIST,
        reason="Keep aisles clear.",
        recorded_by="Sam Safety",
        recorded_at=APPROVED_AT,
    )


def test_another_events_arrangements_and_reservations_are_left_out(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    another_event: EventRequest,
) -> None:
    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE, session=db_session)

    assert (record.venue_arrangements, record.equipment_reservations) == ((), ())


def test_nothing_is_hidden_once_a_confirmed_event_returns_to_approved(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    set_status: Callable[[EventRequestStatus], None],
    arrange: Arrange,
    safety_approved: None,
) -> None:
    """SCRUM-49 AC13: a change withdraws the approval (ADR-0087); the venues stay shown.

    The withdrawn approval is no longer the current check's outcome, so the safety
    section shows none until the new check; the old outcome stays in the history.
    """
    arrange(BookingRequestStatus.APPROVED)
    arrange(BookingRequestStatus.APPROVED)
    set_status(EventRequestStatus.CONFIRMED)
    withdraw_safety_approval(
        saved_event_request.id,
        actor_id=COORDINATOR_ID,
        details={"significant_fields": ["expected_attendance"]},
        session=db_session,
    )
    db_session.commit()

    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE, session=db_session)

    assert record.event_request.status is EventRequestStatus.APPROVED
    statuses = [arrangement.status for arrangement in record.venue_arrangements]
    assert statuses == [BookingRequestStatus.APPROVED, BookingRequestStatus.APPROVED]
    assert record.safety_outcome is None


# --------------------------------------------------------------------------
# How the record route shows it to the organiser
# --------------------------------------------------------------------------


def _everything_on_record(make_event_request: Callable[..., EventRequest]) -> OrganiserEventRecord:
    """A record with one of everything, the arrangement on hold and flagged."""
    event_request = make_event_request(status=EventRequestStatus.APPROVED)
    event_request.programme_notes = "Doors open at 08:30."
    event_request.internal_planning_notes = "Caterer arrives at 07:00."
    held_and_flagged = arrangement_for_record(
        status=BookingRequestStatus.ON_HOLD,
        hold_expires_at=datetime(2026, 10, 30, 9, 0, tzinfo=UTC),
        needs_alternative_venue=True,
        unavailability=[
            UnavailabilityForRecord(
                category=UnavailabilityCategory.MAINTENANCE,
                reason="Aircon repair.",
                starts_at=datetime(2026, 11, 1, 0, 0, tzinfo=UTC),
                ends_at=None,
            )
        ],
        reassessment_flags=[
            ReassessmentForRecord(
                kind=ReassessmentFlagKind.REQUIRES_RECONFIRMATION,
                reason="The date changed.",
            )
        ],
        required_layout="theatre",
        justification="Only hall free that week.",
        decision_reason="Held while the partner confirms.",
    )
    reservation = ReservationAsShown(
        id=21,
        equipment_type_id=1,
        equipment_type_name="Projector",
        quantity=4,
        starts_at=RESERVED_FROM,
        ends_at=RESERVED_TO,
        reserved_by="Tess Tech",
        created_at=RESERVED_FROM,
        needs_attention=False,
        preparation_status=PreparationStatus.READY,
        preparation_notes="All four tested.",
    )
    outcome = SafetyOutcomeAsShown(
        outcome="approved",
        checklist=CHECKLIST,
        reason="Keep aisles clear.",
        recorded_by="Sam Safety",
        recorded_at=APPROVED_AT,
    )
    return OrganiserEventRecord(
        event_request=event_request,
        coordinator=None,
        venue_arrangements=(held_and_flagged,),
        equipment_reservations=(reservation,),
        safety_outcome=outcome,
    )


def test_the_route_sends_the_organiser_every_section_of_the_record(
    open_record_route: Callable[[OrganiserEventRecord], dict[str, Any]],
    make_event_request: Callable[..., EventRequest],
) -> None:
    body = open_record_route(_everything_on_record(make_event_request))

    assert set(body) == RECORD_KEYS
    assert body["programme_notes"] == "Doors open at 08:30."
    assert body["internal_planning_notes"] == "Caterer arrives at 07:00."


def test_the_route_sends_each_arrangement_in_full_in_business_time(
    open_record_route: Callable[[OrganiserEventRecord], dict[str, Any]],
    make_event_request: Callable[..., EventRequest],
) -> None:
    body = open_record_route(_everything_on_record(make_event_request))

    assert body["venue_arrangements"] == [
        {
            "venue_name": "Main Hall",
            "venue_location": "Building A",
            "venue_capacity": 100,
            "venue_facilities": ["projector", "wifi"],
            "venue_accessibility_features": ["wheelchair_access"],
            "starts_at": "2026-11-01T17:00:00+08:00",
            "ends_at": "2026-11-01T17:30:00+08:00",
            "purpose": "Main session",
            "expected_occupancy": 80,
            "required_layout": "theatre",
            "justification": "Only hall free that week.",
            "status": "on_hold",
            "decision_reason": "Held while the partner confirms.",
            "hold_expires_at": "2026-10-30T17:00:00+08:00",
            "needs_alternative_venue": True,
            "unavailability": [
                {
                    "category": "maintenance",
                    "reason": "Aircon repair.",
                    "starts_at": "2026-11-01T08:00:00+08:00",
                    "ends_at": None,
                }
            ],
            "flagged_after_change": False,
            "reassessment_flags": [
                {"kind": "requires_reconfirmation", "reason": "The date changed."}
            ],
            "preparation_status": "not_started",
            "preparation_notes": None,
        }
    ]


def test_the_route_sends_the_reservations_and_the_safety_check_as_the_staff_record_does(
    open_record_route: Callable[[OrganiserEventRecord], dict[str, Any]],
    make_event_request: Callable[..., EventRequest],
) -> None:
    body = open_record_route(_everything_on_record(make_event_request))

    assert body["equipment_reservations"] == [
        {
            "equipment_type_name": "Projector",
            "quantity": 4,
            "starts_at": "2026-11-01T09:00:00+08:00",
            "ends_at": "2026-11-01T17:00:00+08:00",
            "reserved_by": "Tess Tech",
            "preparation_status": "ready",
            "preparation_notes": "All four tested.",
        }
    ]
    assert body["safety_outcome"] == {
        "outcome": "approved",
        "checklist": CHECKLIST,
        "reason": "Keep aisles clear.",
        "recorded_by": "Sam Safety",
        "recorded_at": "2026-10-23T12:30:00+08:00",
    }


def test_the_route_sends_null_for_a_check_with_no_outcome_yet(
    open_record_route: Callable[[OrganiserEventRecord], dict[str, Any]],
    make_event_request: Callable[..., EventRequest],
) -> None:
    record = OrganiserEventRecord(event_request=make_event_request(), coordinator=None)

    body = open_record_route(record)

    assert body["safety_outcome"] is None
    assert (body["venue_arrangements"], body["equipment_reservations"]) == ([], [])


def test_the_coordinators_record_route_is_unchanged(
    call_route: Callable[..., Any],
    replace_services: Callable[..., Any],
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    make_event_request: Callable[..., EventRequest],
) -> None:
    """The coordinator works on the arrangements and the check from their own pages."""
    record = EventRecord(
        event_request=make_event_request(status=EventRequestStatus.CONFIRMED), coordinator=None
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
    organiser_only = {
        "internal_planning_notes",
        "venue_arrangements",
        "equipment_reservations",
        "safety_outcome",
    }
    assert organiser_only.isdisjoint(response.get_json())
