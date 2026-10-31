"""Unit tests for SCRUM-61 AC5: a cancelled event can no longer be edited.

The story's note says each of these already allows only listed statuses, Cancelled
not among them, so no new code is needed, only a test that each one refuses it. Each
test cancels the event through :func:`cancel_event_request`, as the Organiser would,
then tries one action:

* editing the event (SCRUM-33) and its equipment lines (SCRUM-37);
* recording or revising an equipment outcome (SCRUM-48 AC8): in
  ``test_cancel_event.py``, beside AC7;
* withdrawing, changing or cancelling one or all of its venue arrangements, refused by
  the rule that they change only while the event is planned (SCRUM-93 AC10, SCRUM-111
  AC4, ADR-0118), and raising a new one (SCRUM-42);
* registering for it (SCRUM-52).

Runs against ``db_session`` with ``saved_users``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError
from app.modules.auth.models import User
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import (
    ARRANGEMENTS_NOT_IN_PLANNING_MESSAGE,
    EQUIPMENT_NOT_EDITABLE_MESSAGE,
    NOT_EDITABLE_MESSAGE,
    EquipmentNotEditableError,
    RequestNotEditableError,
    add_equipment_line,
    cancel_event_request,
    update_event_request,
)
from app.modules.registration.services import register_for_event
from app.modules.venue import services as venue_services
from app.modules.venue.models import BookingRequestStatus, Venue
from tests.events.cases import Arrange
from tests.venue.conftest import booking_payload

pytestmark = pytest.mark.scrum_61

REFERENCE = "EVR-AAAAAAAA"
ORGANISER_ID = 7
COORDINATOR_ID = 3
#: A fixed "today" before the event, so an edit isn't refused for being in the past.
TODAY = date(2026, 10, 1)
REASON_BODY = {"reason": "Our keynote speaker has withdrawn."}


def _cancel(reference: str, session: Session) -> None:
    cancel_event_request(ORGANISER_ID, reference, REASON_BODY, session=session)


@pytest.fixture()
def cancelled(
    db_session: Session, saved_users: list[User], saved_event_request: EventRequest
) -> EventRequest:
    """``saved_event_request``, approved and then cancelled by its organiser."""
    saved_event_request.status = EventRequestStatus.APPROVED
    db_session.commit()
    _cancel(REFERENCE, db_session)
    return saved_event_request


# --------------------------------------------------------------------------
# The event and its equipment lines (SCRUM-33, SCRUM-37)
# --------------------------------------------------------------------------


def test_the_coordinator_can_no_longer_edit_it(
    db_session: Session, cancelled: EventRequest
) -> None:
    with pytest.raises(RequestNotEditableError) as exc_info:
        update_event_request(
            COORDINATOR_ID, REFERENCE, {"description": "New"}, session=db_session, today=TODAY
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == NOT_EDITABLE_MESSAGE


def test_no_equipment_line_can_be_added(
    db_session: Session,
    cancelled: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
) -> None:
    with pytest.raises(EquipmentNotEditableError) as exc_info:
        add_equipment_line(
            COORDINATOR_ID, REFERENCE, valid_equipment_line_payload, session=db_session
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == EQUIPMENT_NOT_EDITABLE_MESSAGE


# --------------------------------------------------------------------------
# Its venue arrangements (SCRUM-93, SCRUM-111, SCRUM-42)
# --------------------------------------------------------------------------


@pytest.fixture()
def cancelled_with_a_booking(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    arrange: Arrange,
) -> int:
    """An approved event with a booking, then cancelled; returns the booking's id."""
    saved_event_request.status = EventRequestStatus.APPROVED
    db_session.commit()
    booking = arrange(BookingRequestStatus.APPROVED)
    _cancel(REFERENCE, db_session)
    return booking.id


def _withdraw(arrangement_id: int, session: Session) -> None:
    venue_services.withdraw_arrangement(
        REFERENCE, arrangement_id, coordinator_id=COORDINATOR_ID, session=session
    )


def _change(arrangement_id: int, session: Session) -> None:
    venue_services.change_arrangement(
        REFERENCE,
        arrangement_id,
        {"purpose": "Keynote"},
        coordinator_id=COORDINATOR_ID,
        session=session,
    )


def _cancel_booking(arrangement_id: int, session: Session) -> None:
    venue_services.cancel_approved_booking(
        REFERENCE, arrangement_id, REASON_BODY, coordinator_id=COORDINATOR_ID, session=session
    )


def _cancel_all(_arrangement_id: int, session: Session) -> None:
    venue_services.cancel_all_arrangements(
        REFERENCE, REASON_BODY, coordinator_id=COORDINATOR_ID, session=session
    )


@pytest.mark.parametrize(
    "act",
    [_withdraw, _change, _cancel_booking, _cancel_all],
    ids=["withdraw", "change", "cancel-booking", "cancel-all"],
)
def test_its_venue_arrangements_can_no_longer_change(
    db_session: Session,
    cancelled_with_a_booking: int,
    act: Callable[[int, Session], None],
) -> None:
    """SCRUM-93 AC10, SCRUM-111 AC4: refused for the event's status, which it names."""
    with pytest.raises(ConflictError) as exc_info:
        act(cancelled_with_a_booking, db_session)

    assert exc_info.value.message == ARRANGEMENTS_NOT_IN_PLANNING_MESSAGE.format(status="cancelled")


def test_no_new_venue_can_be_requested(
    db_session: Session, cancelled: EventRequest, venue: Venue
) -> None:
    with pytest.raises(ConflictError) as exc_info:
        venue_services.raise_booking_request(
            REFERENCE,
            booking_payload(venue_id=venue.id),
            requested_by=COORDINATOR_ID,
            session=db_session,
        )

    assert exc_info.value.message.endswith("this one is cancelled.")


# --------------------------------------------------------------------------
# Registration (SCRUM-52)
# --------------------------------------------------------------------------


def test_no_new_registration_can_be_made(
    db_session: Session,
    saved_users: list[User],
    saved_attendees: list[User],
    make_open_event: Callable[..., EventRequest],
    now: datetime,
) -> None:
    open_event = make_open_event()
    # Open until it is cancelled: the first Attendee gets a place.
    register_for_event(20, open_event.id, session=db_session, now=now)

    _cancel(open_event.reference, db_session)

    with pytest.raises(NotFoundError):
        register_for_event(21, open_event.id, session=db_session, now=now)
