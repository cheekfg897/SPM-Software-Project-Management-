"""Unit tests for SCRUM-97 "Submit an event for operational safety check" (part A).

AC1: once every active venue arrangement is Approved and every equipment request has
an outcome from Technical Support, the assigned coordinator moves the approved event
to Safety Review. A Pending or Rejected arrangement holds it back; a Withdrawn one is
ignored. AC2: an event with no equipment requests passes the equipment check. An
event with no venue arranged at all is held back (ADR-0047). The move is written to
the event history; a refusal changes nothing.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, assigned to Event Coordinator 3), so the venue and equipment
checks are real SQL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    NOT_APPROVED_FOR_SAFETY_REVIEW_MESSAGE,
    SAFETY_REVIEW_NOT_READY_MESSAGE,
    SafetyReviewNotAllowedError,
    submit_for_safety_review,
)
from app.modules.venue.models import BookingRequestStatus, Venue, VenueBookingRequest

pytestmark = pytest.mark.scrum_97

Arrange = Callable[[BookingRequestStatus], VenueBookingRequest]
AddLine = Callable[[int | None], EventEquipmentLine]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
ReloadEventRequest = Callable[[int], EventRequest]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9


@pytest.fixture()
def approved_event(
    saved_users: list[User], saved_event_request: EventRequest, save: Callable[..., None]
) -> EventRequest:
    """``saved_event_request``, approved by its coordinator, with the users saved."""
    saved_event_request.status = EventRequestStatus.APPROVED
    save(saved_event_request)
    return saved_event_request


@pytest.fixture()
def arrange(approved_event: EventRequest, venue: Venue, save: Callable[..., None]) -> Arrange:
    """Save a venue arrangement for ``approved_event`` with the given status.

    Each one starts an hour after the last, so two Pending ones never share a period.
    """
    arranged: list[VenueBookingRequest] = []

    def _arrange(status: BookingRequestStatus) -> VenueBookingRequest:
        hour = 9 + len(arranged)
        arrangement = VenueBookingRequest(
            event_id=approved_event.id,
            venue_id=venue.id,
            starts_at=datetime(2026, 11, 1, hour, tzinfo=timezone.utc),
            ends_at=datetime(2026, 11, 1, hour, 30, tzinfo=timezone.utc),
            purpose="Main session",
            expected_occupancy=80,
            status=status,
            requested_by=COORDINATOR_ID,
        )
        save(arrangement)
        arranged.append(arrangement)
        return arrangement

    return _arrange


@pytest.fixture()
def add_line(
    approved_event: EventRequest,
    make_equipment_type: Callable[..., EquipmentType],
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
) -> AddLine:
    """Save a request for 2 units on ``approved_event``, ``provided_quantity`` as given.

    ``None`` means Technical Support has not recorded an outcome yet (ADR-0040).
    Each request is for its own equipment type.
    """
    added: list[EventEquipmentLine] = []

    def _add(provided_quantity: int | None) -> EventEquipmentLine:
        equipment_type = make_equipment_type(name=f"Item {len(added)}")
        save(equipment_type)
        line = make_equipment_line(approved_event, equipment_type)
        if provided_quantity is not None:
            line.provided_quantity = provided_quantity
            line.status = EquipmentLineStatus.FULFILLED
        save(line)
        added.append(line)
        return line

    return _add


def _submit(session: Session, coordinator_id: int = COORDINATOR_ID) -> EventRequest:
    return submit_for_safety_review(coordinator_id, REFERENCE, session=session)


def _refusal(session: Session) -> SafetyReviewNotAllowedError:
    with pytest.raises(SafetyReviewNotAllowedError) as exc_info:
        _submit(session)
    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "safety_review_not_allowed")
    return refused


def _assert_still_approved(
    approved_event: EventRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
) -> None:
    assert reload_event_request(approved_event.id).status is EventRequestStatus.APPROVED
    assert history_of(approved_event.id) == []


# --------------------------------------------------------------------------
# AC1 — every arrangement Approved and every outcome recorded moves it on
# --------------------------------------------------------------------------


def test_an_event_ready_on_both_counts_moves_to_safety_review(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    add_line: AddLine,
    reload_event_request: ReloadEventRequest,
) -> None:
    arrange(BookingRequestStatus.APPROVED)
    add_line(2)

    submitted = _submit(db_session)

    assert submitted.status is EventRequestStatus.SAFETY_REVIEW
    assert reload_event_request(approved_event.id).status is EventRequestStatus.SAFETY_REVIEW


def test_the_move_is_written_to_the_event_history(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    history_of: HistoryOf,
) -> None:
    arrange(BookingRequestStatus.APPROVED)

    _submit(db_session)

    assert history_of(approved_event.id) == [
        (EventHistoryKind.SAFETY_REVIEW_REQUESTED, COORDINATOR_ID, None)
    ]


@pytest.mark.parametrize("status", [BookingRequestStatus.PENDING, BookingRequestStatus.REJECTED])
def test_an_arrangement_that_is_not_approved_holds_the_event_back(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    status: BookingRequestStatus,
) -> None:
    arrange(BookingRequestStatus.APPROVED)
    held = arrange(status)

    refused = _refusal(db_session)

    assert refused.message == SAFETY_REVIEW_NOT_READY_MESSAGE
    assert refused.details == {
        "venue_arrangements": [f"Venue arrangement {held.id} is {status.value}."]
    }
    _assert_still_approved(approved_event, reload_event_request, history_of)


def test_a_withdrawn_arrangement_is_ignored(db_session: Session, arrange: Arrange) -> None:
    arrange(BookingRequestStatus.APPROVED)
    arrange(BookingRequestStatus.WITHDRAWN)

    assert _submit(db_session).status is EventRequestStatus.SAFETY_REVIEW


def test_an_equipment_request_without_an_outcome_holds_the_event_back(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    add_line: AddLine,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
) -> None:
    arrange(BookingRequestStatus.APPROVED)
    add_line(2)
    waiting = add_line(None)

    refused = _refusal(db_session)

    assert refused.details == {
        "equipment": [f"Equipment request {waiting.id} has no outcome from Technical Support."]
    }
    _assert_still_approved(approved_event, reload_event_request, history_of)


# --------------------------------------------------------------------------
# AC2 — equipment is optional; ADR-0047 — a venue is not
# --------------------------------------------------------------------------


def test_an_event_with_no_equipment_requests_passes_the_equipment_check(
    db_session: Session, arrange: Arrange
) -> None:
    arrange(BookingRequestStatus.APPROVED)

    assert _submit(db_session).status is EventRequestStatus.SAFETY_REVIEW


def test_an_event_with_no_venue_arranged_is_held_back(
    db_session: Session,
    approved_event: EventRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
) -> None:
    refused = _refusal(db_session)

    assert refused.details == {"venue_arrangements": ["The event has no venue arranged."]}
    _assert_still_approved(approved_event, reload_event_request, history_of)


# --------------------------------------------------------------------------
# Who may, and from which status (ADR-0047)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        EventRequestStatus.SUBMITTED,
        EventRequestStatus.UNDER_REVIEW,
        EventRequestStatus.SAFETY_REVIEW,
        EventRequestStatus.CONFIRMED,
    ],
    ids=lambda status: status.value,
)
def test_only_an_approved_event_can_be_submitted(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    save: Callable[..., None],
    status: EventRequestStatus,
) -> None:
    arrange(BookingRequestStatus.APPROVED)
    approved_event.status = status
    save(approved_event)

    refused = _refusal(db_session)

    assert refused.message == NOT_APPROVED_FOR_SAFETY_REVIEW_MESSAGE
    assert refused.details is None


def test_a_coordinator_not_assigned_to_the_event_gets_a_404(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
) -> None:
    arrange(BookingRequestStatus.APPROVED)

    with pytest.raises(NotFoundError):
        _submit(db_session, OTHER_COORDINATOR_ID)

    _assert_still_approved(approved_event, reload_event_request, history_of)
