"""Unit tests for the read-only event record internal users open (SCRUM-24 AC9, AC10).

AC9 (changed 19 Oct): Venue Staff, Technical Support Staff and the Safety Officer can
open the record of any submitted event, read-only: its details, venue arrangements,
equipment, safety outcome, history and internal notes. AC10: the Event Coordinator
Lead can open every event, unassigned and assigned. SCRUM-84 AC2 and SCRUM-85 AC2: the
venue and equipment preparation details are visible to these internal users too.
Drafts stay private to their author (SCRUM-20, ADR-0024). Decisions in ADR-0095.

The record is read with ``get_staff_event_record``; who may call it is the route's
check (``test_staff_event_record_routes.py``). The service tests run against
``db_session``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment.models import EquipmentReservation, EquipmentType, PreparationStatus
from app.modules.events.models import (
    EquipmentLineStatus,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    CoordinatorContact,
    DecisionAsShown,
    EquipmentLineOnRecord,
    SafetyOutcomeAsShown,
    get_staff_event_record,
)
from app.modules.venue.models import (
    BookingRequestStatus,
    PreparationStatus as VenuePreparationStatus,
    Venue,
)
from tests.events.cases import (
    DRAFT_REFERENCE,
    NON_DRAFT_STATUSES,
    AddLine,
    Arrange,
    SaveArrangement,
    arrangement_for_record,
)

pytestmark = pytest.mark.scrum_24

RecordEntry = Callable[..., None]

REFERENCE = "EVR-AAAAAAAA"
SAFETY_OFFICER_ID = 11
CHECKLIST = {
    "attendance_vs_capacity": "250 expected; the hall holds 300.",
    "venue_layout": "Theatre layout with two aisles.",
    "emergency_access": "Both fire exits kept clear.",
    "accessibility": "Step-free entrance at the side.",
    "equipment_placement": "Cables taped down along the walls.",
    "crowd_movement": "Staggered entry from 08:30.",
    "venue_restrictions": "No open flames.",
}
FIRST_CHECK_AT = datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc)
SECOND_CHECK_AT = datetime(2026, 10, 2, 2, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 3, 2, 0, tzinfo=timezone.utc)


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
def record_outcome(record_entry: RecordEntry, safety_officer: User) -> Callable[..., None]:
    """Save the Safety Officer's outcome on ``saved_event_request`` at a pinned time."""

    def _record(outcome: str, occurred_at: datetime, reason: str | None = None) -> None:
        record_entry(
            EventHistoryKind.SAFETY_OUTCOME_RECORDED,
            occurred_at,
            actor_id=SAFETY_OFFICER_ID,
            details={"outcome": outcome, "checklist": CHECKLIST, "reason": reason},
        )

    return _record


def _event_of_status(
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
    status: EventRequestStatus,
) -> EventRequest:
    """Save ``EVR-AAAAAAAA`` in ``status``, with no coordinator yet."""
    event_request = make_event_request(status=status)
    save(event_request)
    return event_request


# --------------------------------------------------------------------------
# AC9, AC10 — any submitted event opens, assigned or not; a draft never does
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", NON_DRAFT_STATUSES, ids=lambda status: status.value)
def test_any_submitted_event_opens_even_with_no_coordinator(
    db_session: Session,
    saved_users: list[User],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
    status: EventRequestStatus,
) -> None:
    _event_of_status(make_event_request, save, status)

    staff_record = get_staff_event_record(" evr-aaaaaaaa ", session=db_session)

    assert staff_record.record.event_request.reference == REFERENCE
    assert staff_record.record.event_request.status is status
    assert staff_record.record.coordinator is None


def test_an_assigned_event_shows_its_coordinator(
    db_session: Session, saved_users: list[User], saved_event_request: EventRequest
) -> None:
    staff_record = get_staff_event_record(REFERENCE, session=db_session)

    assert staff_record.record.coordinator == CoordinatorContact(
        full_name="Coordinator Three", email="coordinator3@example.com"
    )


@pytest.mark.parametrize("reference", [DRAFT_REFERENCE, "EVR-ZZZZZZZZ"], ids=["draft", "unknown"])
def test_a_draft_or_an_unknown_reference_is_not_found(
    db_session: Session,
    saved_users: list[User],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
    reference: str,
) -> None:
    save(make_event_request(reference=DRAFT_REFERENCE, status=EventRequestStatus.DRAFT))

    with pytest.raises(NotFoundError) as exc_info:
        get_staff_event_record(reference, session=db_session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Event request not found."


def test_the_record_shows_the_decision_as_the_coordinators_record_does(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    record_entry: RecordEntry,
) -> None:
    record_entry(
        EventHistoryKind.DECISION_RECORDED,
        FIRST_CHECK_AT,
        actor_id=3,
        details={"outcome": "approved", "reason": None},
    )

    staff_record = get_staff_event_record(REFERENCE, session=db_session)

    assert staff_record.record.decision == DecisionAsShown(
        outcome="approved", reason=None, decided_by="Coordinator Three", decided_at=FIRST_CHECK_AT
    )


# --------------------------------------------------------------------------
# AC9, SCRUM-84 AC2 — the venue arrangements with their preparation
# --------------------------------------------------------------------------


def test_the_record_holds_each_venue_arrangement_with_its_preparation(
    db_session: Session, saved_users: list[User], arrange: Arrange
) -> None:
    arrangement = arrange(BookingRequestStatus.APPROVED)
    arrangement.preparation_status = VenuePreparationStatus.READY
    arrangement.preparation_notes = "Stage built."
    db_session.commit()

    staff_record = get_staff_event_record(REFERENCE, session=db_session)

    assert staff_record.venue_arrangements == [
        arrangement_for_record(
            preparation_status=VenuePreparationStatus.READY, preparation_notes="Stage built."
        )
    ]


def test_another_events_venue_arrangements_are_left_out(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    make_event_request: Callable[..., EventRequest],
    venue: Venue,
    save: Callable[..., None],
    save_arrangement: SaveArrangement,
) -> None:
    other_event = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=3)
    save(other_event)
    save_arrangement(other_event, venue, BookingRequestStatus.APPROVED)

    staff_record = get_staff_event_record(REFERENCE, session=db_session)

    assert staff_record.venue_arrangements == []


# --------------------------------------------------------------------------
# AC9, SCRUM-85 AC2 — the equipment, its outcome and its reservations' preparation
# --------------------------------------------------------------------------


@pytest.mark.scrum_48
def test_the_record_holds_each_equipment_request_with_its_outcome_and_reviewer(
    db_session: Session, saved_users: list[User], add_line: AddLine
) -> None:
    """SCRUM-48 AC5: who reviewed the line and when, by name (ADR-0105)."""
    line = add_line(2)
    line.reviewed_by = 5
    line.reviewed_at = FIRST_CHECK_AT
    db_session.commit()

    staff_record = get_staff_event_record(REFERENCE, session=db_session)

    assert staff_record.equipment_lines == [
        EquipmentLineOnRecord(
            equipment_type_name="Item 0",
            quantity=2,
            notes="Needs HDMI",
            status=EquipmentLineStatus.FULFILLED,
            provided_quantity=2,
            shortfall=0,
            outcome_note=None,
            reviewed_by="Alice Example",
            reviewed_at=FIRST_CHECK_AT,
        )
    ]


def test_the_record_holds_the_events_reservations_with_their_preparation(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    save: Callable[..., None],
) -> None:
    held: dict[str, Any] = {
        "equipment_type_id": equipment_type.id,
        "starts_at": FIRST_CHECK_AT,
        "ends_at": SECOND_CHECK_AT,
        "reserved_by": 5,
    }
    reservation = EquipmentReservation(event_id=saved_event_request.id, quantity=4, **held)
    reservation.preparation_status = PreparationStatus.IN_PROGRESS
    reservation.preparation_notes = "Two of four tested."
    another_events = EquipmentReservation(event_id=saved_event_request.id + 1, quantity=1, **held)
    save(reservation, another_events)

    staff_record = get_staff_event_record(REFERENCE, session=db_session)

    shown = []
    for reserved in staff_record.equipment_reservations:
        shown.append(
            (
                reserved.equipment_type_name,
                reserved.quantity,
                reserved.preparation_status,
                reserved.preparation_notes,
            )
        )
    assert shown == [("Projector", 4, PreparationStatus.IN_PROGRESS, "Two of four tested.")]


# --------------------------------------------------------------------------
# AC9 — the safety outcome of the event's current check
# --------------------------------------------------------------------------


def test_an_event_never_checked_has_no_safety_outcome(
    db_session: Session, saved_users: list[User], saved_event_request: EventRequest
) -> None:
    staff_record = get_staff_event_record(REFERENCE, session=db_session)

    assert staff_record.safety_outcome is None


def test_the_record_shows_the_latest_safety_outcome_with_its_checklist(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    record_outcome: Callable[..., None],
) -> None:
    record_outcome("changes_requested", FIRST_CHECK_AT, "Add a second exit.")
    record_outcome("approved", SECOND_CHECK_AT)

    staff_record = get_staff_event_record(REFERENCE, session=db_session)

    assert staff_record.safety_outcome == SafetyOutcomeAsShown(
        outcome="approved",
        checklist=CHECKLIST,
        reason=None,
        recorded_by="Sam Safety",
        recorded_at=SECOND_CHECK_AT,
    )


def test_the_record_shows_the_reason_the_officer_gave_for_a_current_refusal(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    record_outcome: Callable[..., None],
) -> None:
    """The current outcome's own reason, not an earlier one's (ADR-0095 decision 5)."""
    record_outcome("rejected", FIRST_CHECK_AT, "No second fire exit.")

    staff_record = get_staff_event_record(REFERENCE, session=db_session)

    assert staff_record.safety_outcome == SafetyOutcomeAsShown(
        outcome="rejected",
        checklist=CHECKLIST,
        reason="No second fire exit.",
        recorded_by="Sam Safety",
        recorded_at=FIRST_CHECK_AT,
    )


@pytest.mark.parametrize(
    "later_kind",
    [EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN, EventHistoryKind.SAFETY_REVIEW_REQUESTED],
    ids=lambda kind: kind.value,
)
def test_an_outcome_a_later_check_replaces_is_no_longer_shown(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    record_outcome: Callable[..., None],
    record_entry: RecordEntry,
    later_kind: EventHistoryKind,
) -> None:
    """A withdrawn approval or a new check leaves the current check with no outcome.

    The old outcome stays in the history (ADR-0047, ADR-0087, ADR-0095).
    """
    record_outcome("approved", FIRST_CHECK_AT)
    record_entry(later_kind, LATER, actor_id=3, details={})

    staff_record = get_staff_event_record(REFERENCE, session=db_session)

    assert staff_record.safety_outcome is None
