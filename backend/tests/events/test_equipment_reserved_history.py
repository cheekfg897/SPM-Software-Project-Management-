"""Unit tests for what SCRUM-46 "Reserve equipment" asks of the events module.

Reserving needs the event's id to link the reservation to (AC4) and whether the event
still takes reservations: one that is completed, cancelled or rejected does not. It
gets both from ``get_event_equipment_need`` rather than from the event models.
``record_equipment_reserved`` writes the audit entry, an ``equipment_reserved`` history
entry, into the caller's transaction; internal staff see it in the event's history and
organisers never do.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    EQUIPMENT_NOT_NEEDED_STATUSES,
    RESERVATIONS_CLOSED_MESSAGE,
    get_event_equipment_need,
    list_event_history,
    record_equipment_reserved,
)

pytestmark = pytest.mark.scrum_46

Save = Callable[..., None]

REFERENCE = "EVR-AAAAAAAA"
TECHNICAL_SUPPORT_ID = 5
RESERVED_DETAILS = {
    "equipment_type_id": 2,
    "equipment_type_name": "Projector",
    "quantity": 4,
    "reservation_id": 11,
}


def _record_reservation(db_session: Session, event_request: EventRequest) -> None:
    record_equipment_reserved(
        event_request.id, RESERVED_DETAILS, actor_id=TECHNICAL_SUPPORT_ID, session=db_session
    )


def test_the_need_carries_the_events_id(
    db_session: Session, saved_event_request: EventRequest
) -> None:
    need = get_event_equipment_need(REFERENCE, session=db_session)

    assert need.event_id == saved_event_request.id


@pytest.mark.parametrize(
    ("status", "accepts_reservations"),
    [
        (EventRequestStatus.SUBMITTED, True),
        (EventRequestStatus.UNDER_REVIEW, True),
        (EventRequestStatus.AWAITING_CLARIFICATION, True),
        (EventRequestStatus.APPROVED, True),
        (EventRequestStatus.CONFIRMED, True),
        (EventRequestStatus.COMPLETED, False),
        (EventRequestStatus.CANCELLED, False),
        (EventRequestStatus.REJECTED, False),
    ],
)
def test_only_an_event_that_is_still_going_ahead_accepts_reservations(
    db_session: Session,
    saved_event_request: EventRequest,
    save: Save,
    status: EventRequestStatus,
    accepts_reservations: bool,
) -> None:
    saved_event_request.status = status
    save(saved_event_request)

    need = get_event_equipment_need(REFERENCE, session=db_session)

    assert need.accepts_reservations is accepts_reservations


def test_the_entry_names_the_equipment_and_who_reserved_it(
    db_session: Session, saved_event_request: EventRequest
) -> None:
    _record_reservation(db_session, saved_event_request)
    db_session.commit()

    db_session.expire_all()
    entry = db_session.scalars(select(EventHistoryEntry)).one()
    assert entry.event_request_id == saved_event_request.id
    assert entry.kind is EventHistoryKind.EQUIPMENT_RESERVED
    assert entry.actor_id == TECHNICAL_SUPPORT_ID
    assert entry.details == RESERVED_DETAILS


def test_the_entry_is_not_committed_on_its_own(
    db_session: Session, saved_event_request: EventRequest
) -> None:
    # It rides in the reservation's transaction: rolled back with it, it is gone.
    _record_reservation(db_session, saved_event_request)
    db_session.rollback()

    assert db_session.scalars(select(EventHistoryEntry)).all() == []


def test_internal_staff_see_the_reservation_in_the_history(
    db_session: Session, saved_users: list[User], saved_event_request: EventRequest
) -> None:
    _record_reservation(db_session, saved_event_request)
    db_session.commit()

    entries = list_event_history(
        TECHNICAL_SUPPORT_ID, REFERENCE, viewer_role=Role.TECHNICAL_SUPPORT_STAFF
    )

    assert [(entry.kind, entry.actor_name, entry.details) for entry in entries] == [
        (EventHistoryKind.EQUIPMENT_RESERVED, "Alice Example", RESERVED_DETAILS)
    ]


def test_the_organiser_sees_the_reservation_in_the_history(
    db_session: Session, saved_users: list[User], saved_event_request: EventRequest
) -> None:
    """Nothing on the record is hidden from the organiser (SCRUM-24 AC10, ADR-0104)."""
    _record_reservation(db_session, saved_event_request)
    db_session.commit()

    entries = list_event_history(7, REFERENCE, viewer_role=Role.EVENT_ORGANISER)

    assert [(entry.kind, entry.actor_name, entry.details) for entry in entries] == [
        (EventHistoryKind.EQUIPMENT_RESERVED, "Alice Example", RESERVED_DETAILS)
    ]


def test_the_closed_message_names_every_status_that_closes_reservations() -> None:
    for status in EQUIPMENT_NOT_NEEDED_STATUSES:
        assert status.value in RESERVATIONS_CLOSED_MESSAGE
