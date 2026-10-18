"""Unit tests for SCRUM-85 — Technical Support record a reservation's preparation.

Any Technical Support member records a preparation status and notes against a
reservation (AC1, ADR-0050). The details are saved on the reservation, which the
coordinator reads with the event's reservations (AC2), and nothing else of the
reservation changes (AC3). Each update writes a history entry naming the user and the
time (AC4). Nothing is recorded until the Safety Officer has approved the event (AC5).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.auth.permissions import Role
from app.modules.equipment import services
from app.modules.equipment.models import EquipmentReservation, EquipmentType, PreparationStatus
from app.modules.events import services as event_services
from app.modules.events.models import EventHistoryEntry, EventHistoryKind, EventRequest
from tests.equipment.conftest import MakeReservation, approve_safety

pytestmark = pytest.mark.scrum_85

TECHNICAL_SUPPORT_ID = 5
#: A Technical Support id no fixture uses, so a hard-coded actor can't pass by chance.
OTHER_TECHNICAL_SUPPORT_ID = 42
COORDINATOR_ID = 3
STARTS_AT = datetime(2026, 11, 3, 1, 0, tzinfo=UTC)
ENDS_AT = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)
IN_PROGRESS = {"status": "in_progress", "notes": "Projector mounted, cables to run."}


@pytest.fixture()
def reservation(
    equipment_type: EquipmentType,
    saved_event_request: EventRequest,
    make_reservation: MakeReservation,
    save: Callable[..., None],
) -> EquipmentReservation:
    """A reservation of 4 units for the saved event, which the officer has approved."""
    reservation = make_reservation(equipment_type, 4, STARTS_AT, ENDS_AT)
    save(reservation)
    approve_safety(saved_event_request, save)
    return reservation


def _record(reservation: EquipmentReservation, payload: dict[str, str], session: Session) -> None:
    services.update_preparation_details(
        reservation.id, payload, updated_by=TECHNICAL_SUPPORT_ID, session=session
    )


def _preparation_entries(session: Session) -> list[EventHistoryEntry]:
    kind = EventHistoryKind.EQUIPMENT_PREPARATION_UPDATED
    return list(session.scalars(select(EventHistoryEntry).where(EventHistoryEntry.kind == kind)))


def test_technical_support_record_a_status_and_notes_on_a_reservation(
    db_session: Session, reservation: EquipmentReservation
) -> None:
    """AC1."""
    shown = services.update_preparation_details(
        reservation.id, IN_PROGRESS, updated_by=TECHNICAL_SUPPORT_ID, session=db_session
    )

    assert shown.preparation_status is PreparationStatus.IN_PROGRESS
    assert shown.preparation_notes == "Projector mounted, cables to run."
    assert reservation.preparation_status is PreparationStatus.IN_PROGRESS


def test_a_reservation_starts_as_not_started_with_no_notes(
    reservation: EquipmentReservation,
) -> None:
    assert reservation.preparation_status is PreparationStatus.NOT_STARTED
    assert reservation.preparation_notes is None


def test_the_next_update_replaces_the_details_and_notes_may_be_left_out(
    db_session: Session, reservation: EquipmentReservation
) -> None:
    _record(reservation, IN_PROGRESS, db_session)

    _record(reservation, {"status": "ready"}, db_session)

    assert reservation.preparation_status is PreparationStatus.READY
    assert reservation.preparation_notes is None


def test_the_coordinator_reads_the_details_with_the_events_reservations(
    db_session: Session, reservation: EquipmentReservation, saved_event_request: EventRequest
) -> None:
    """AC2: through the list of the event's reservations."""
    _record(reservation, IN_PROGRESS, db_session)

    [listed] = services.list_reservations_for_event(
        COORDINATOR_ID,
        saved_event_request.reference,
        viewer_role=Role.EVENT_COORDINATOR,
        session=db_session,
    )

    assert listed.preparation_status is PreparationStatus.IN_PROGRESS
    assert listed.preparation_notes == "Projector mounted, cables to run."


def test_other_internal_users_read_the_details_in_the_events_history(
    db_session: Session, reservation: EquipmentReservation, saved_event_request: EventRequest
) -> None:
    """AC2: the history entry carries the status and notes for every internal role."""
    _record(reservation, IN_PROGRESS, db_session)

    history = event_services.list_event_history(
        99, saved_event_request.reference, viewer_role=Role.VENUE_STAFF, session=db_session
    )

    [entry] = [
        shown for shown in history if shown.kind is EventHistoryKind.EQUIPMENT_PREPARATION_UPDATED
    ]
    assert entry.details["status"] == "in_progress"
    assert entry.details["notes"] == "Projector mounted, cables to run."


@pytest.mark.parametrize("field", ["quantity", "equipment_type_id", "event_id", "reserved_by"])
def test_any_other_field_of_the_reservation_is_refused(
    db_session: Session, reservation: EquipmentReservation, field: str
) -> None:
    """AC3: the payload carries the preparation details and nothing else."""
    with pytest.raises(ValidationError) as caught:
        _record(reservation, {**IN_PROGRESS, field: "1"}, db_session)

    assert set(caught.value.details) == {field}
    assert reservation.quantity == 4


def test_each_update_records_who_and_when(
    db_session: Session,
    equipment_type: EquipmentType,
    saved_event_request: EventRequest,
    make_event_request: Callable[..., EventRequest],
    make_reservation: MakeReservation,
    save: Callable[..., None],
) -> None:
    """AC4: one history entry per update, with the user, the time and the details.

    The reservation is a second event's, saved after two of the first event's, so the
    reservation, its event and its equipment type have different ids and a mixed-up
    id shows. The update is made by user 42, whom no fixture uses.
    """
    event = make_event_request(reference="EVR-BBBBBBBB")
    save(event)
    save(make_reservation(equipment_type, 1, STARTS_AT, ENDS_AT))
    save(make_reservation(equipment_type, 1, STARTS_AT, ENDS_AT))
    reservation = make_reservation(equipment_type, 4, STARTS_AT, ENDS_AT)
    reservation.event_id = event.id
    save(reservation)
    approve_safety(event, save)
    assert len({reservation.id, event.id, equipment_type.id}) == 3
    before = datetime.now(UTC)

    for payload in (IN_PROGRESS, {"status": "ready"}):
        services.update_preparation_details(
            reservation.id, payload, updated_by=OTHER_TECHNICAL_SUPPORT_ID, session=db_session
        )

    first, second = _preparation_entries(db_session)
    assert first.event_request_id == event.id
    assert first.actor_id == OTHER_TECHNICAL_SUPPORT_ID
    assert first.occurred_at.replace(tzinfo=UTC) >= before
    assert first.details == {
        "reservation_id": reservation.id,
        "equipment_type_id": equipment_type.id,
        "equipment_type_name": equipment_type.name,
        "status": "in_progress",
        "notes": "Projector mounted, cables to run.",
    }
    assert second.details["status"] == "ready"


def test_the_details_and_their_entry_are_committed(
    db_session: Session, reservation: EquipmentReservation
) -> None:
    """AC4: a rollback after the update leaves both the details and the entry saved."""
    _record(reservation, IN_PROGRESS, db_session)

    db_session.rollback()

    reloaded = db_session.get(EquipmentReservation, reservation.id)
    assert reloaded is not None
    assert reloaded.preparation_status is PreparationStatus.IN_PROGRESS
    assert len(_preparation_entries(db_session)) == 1


def test_nothing_is_recorded_before_the_safety_officer_approves(
    db_session: Session,
    equipment_type: EquipmentType,
    saved_event_request: EventRequest,
    make_reservation: MakeReservation,
    save: Callable[..., None],
) -> None:
    """AC5."""
    unapproved = make_reservation(equipment_type, 4, STARTS_AT, ENDS_AT)
    save(unapproved)

    with pytest.raises(ConflictError) as caught:
        _record(unapproved, IN_PROGRESS, db_session)

    assert caught.value.message == services.PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE
    assert unapproved.preparation_status is PreparationStatus.NOT_STARTED
    assert _preparation_entries(db_session) == []


def test_notes_of_the_maximum_length_are_kept_and_one_more_is_refused(
    db_session: Session, reservation: EquipmentReservation
) -> None:
    _record(reservation, {"status": "ready", "notes": f" {'x' * 1000} "}, db_session)
    with pytest.raises(ValidationError) as caught:
        _record(reservation, {"status": "ready", "notes": "x" * 1001}, db_session)

    assert reservation.preparation_notes == "x" * 1000
    assert caught.value.details == {"notes": ["Notes must be at most 1000 characters."]}


def test_an_unknown_reservation_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        services.update_preparation_details(
            404, IN_PROGRESS, updated_by=TECHNICAL_SUPPORT_ID, session=db_session
        )


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"notes": "Cables run."}, "status"),
        ({"status": "finished"}, "status"),
        ({"status": "ready", "notes": "   "}, "notes"),
    ],
    ids=["no status", "unknown status", "blank notes"],
)
def test_an_invalid_payload_is_a_400_naming_the_field(
    db_session: Session, reservation: EquipmentReservation, payload: dict[str, str], field: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        _record(reservation, payload, db_session)

    assert set(caught.value.details) == {field}
    assert _preparation_entries(db_session) == []
