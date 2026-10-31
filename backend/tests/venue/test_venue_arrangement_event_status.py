"""Unit tests for SCRUM-93 AC10 — arrangements change only while the event is planned.

The coordinator can withdraw or change an arrangement, or cancel all of them, only
while the event is Approved or in Safety Review (ADR-0118). Any other status is a 409
whose message names it; nothing is written. A draft is never found (ADR-0024).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, Venue
from tests.venue.conftest import (
    ARRANGEMENT_ACTIONS,
    COORDINATOR_ID,
    ArrangementAction,
    SavedEvent,
    cancel_all_as_coordinator,
    change_purpose_as_coordinator,
    history_entries,
    raise_booking,
    reload_request,
    withdraw_as_coordinator,
)

pytestmark = pytest.mark.scrum_93

#: The statuses in which the event is being planned, written out (ADR-0118).
PLANNING = [EventRequestStatus.APPROVED, EventRequestStatus.SAFETY_REVIEW]
#: Every other status but a draft, which is never found; built from the enum, so a
#: status added later is refused until it is placed.
NOT_PLANNING = [
    status
    for status in EventRequestStatus
    if status not in PLANNING and status is not EventRequestStatus.DRAFT
]
#: An id no arrangement has.
UNKNOWN_ARRANGEMENT_ID = 9999


def _refusal(status: EventRequestStatus) -> str:
    return (
        "Only an approved event or one in Safety Review can have its venue arrangements"
        f" withdrawn, changed or cancelled; this one is {status.value}."
    )


@pytest.fixture()
def event_with_arrangement(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> Callable[[EventRequestStatus], tuple[EventRequest, int]]:
    """An event with one pending arrangement, then moved to ``status``."""

    def _make(status: EventRequestStatus) -> tuple[EventRequest, int]:
        event = saved_event()
        arrangement = raise_booking(venue, event, db_session)
        event.status = status
        db_session.commit()
        return event, arrangement.id

    return _make


@pytest.mark.parametrize("action", ARRANGEMENT_ACTIONS)
@pytest.mark.parametrize("status", NOT_PLANNING, ids=lambda status: status.value)
def test_an_event_that_is_not_being_planned_refuses_the_action_naming_its_status(
    db_session: Session,
    event_with_arrangement: Callable[[EventRequestStatus], tuple[EventRequest, int]],
    action: ArrangementAction,
    status: EventRequestStatus,
) -> None:
    event, arrangement_id = event_with_arrangement(status)
    entries_before = len(history_entries(db_session, event.id))

    with pytest.raises(ConflictError) as caught:
        action(event, arrangement_id, db_session)

    assert caught.value.message == _refusal(status)
    untouched = reload_request(db_session, arrangement_id)
    assert (untouched.status, untouched.purpose) == (BookingRequestStatus.PENDING, "Main hall")
    assert len(history_entries(db_session, event.id)) == entries_before


@pytest.mark.parametrize(
    ("action", "status_after", "purpose_after"),
    [
        pytest.param(
            withdraw_as_coordinator, BookingRequestStatus.WITHDRAWN, "Main hall", id="withdraw"
        ),
        pytest.param(
            change_purpose_as_coordinator,
            BookingRequestStatus.PENDING,
            "Opening plenary",
            id="change",
        ),
        pytest.param(
            cancel_all_as_coordinator, BookingRequestStatus.WITHDRAWN, "Main hall", id="cancel all"
        ),
    ],
)
@pytest.mark.parametrize("status", PLANNING, ids=lambda status: status.value)
def test_an_event_being_planned_allows_the_action(
    db_session: Session,
    event_with_arrangement: Callable[[EventRequestStatus], tuple[EventRequest, int]],
    action: ArrangementAction,
    status_after: BookingRequestStatus,
    purpose_after: str,
    status: EventRequestStatus,
) -> None:
    event, arrangement_id = event_with_arrangement(status)

    action(event, arrangement_id, db_session)

    acted_on = reload_request(db_session, arrangement_id)
    assert (acted_on.status, acted_on.purpose) == (status_after, purpose_after)


@pytest.mark.parametrize("action", ARRANGEMENT_ACTIONS)
def test_a_draft_is_not_found(
    db_session: Session,
    event_with_arrangement: Callable[[EventRequestStatus], tuple[EventRequest, int]],
    action: ArrangementAction,
) -> None:
    event, arrangement_id = event_with_arrangement(EventRequestStatus.DRAFT)

    with pytest.raises(NotFoundError):
        action(event, arrangement_id, db_session)


@pytest.mark.parametrize(
    "action",
    [
        pytest.param(withdraw_as_coordinator, id="withdraw"),
        pytest.param(change_purpose_as_coordinator, id="change"),
    ],
)
def test_the_event_status_is_checked_before_the_arrangement(
    db_session: Session,
    event_with_arrangement: Callable[[EventRequestStatus], tuple[EventRequest, int]],
    action: ArrangementAction,
) -> None:
    """An unknown arrangement on a Confirmed event is refused for the event's status."""
    event, _ = event_with_arrangement(EventRequestStatus.CONFIRMED)

    with pytest.raises(ConflictError) as caught:
        action(event, UNKNOWN_ARRANGEMENT_ID, db_session)

    assert caught.value.message == _refusal(EventRequestStatus.CONFIRMED)


def test_a_change_names_a_bad_field_before_looking_at_the_event(
    db_session: Session,
    event_with_arrangement: Callable[[EventRequestStatus], tuple[EventRequest, int]],
) -> None:
    """The body is checked first, as before AC10; the contract tests pin it."""
    event, arrangement_id = event_with_arrangement(EventRequestStatus.CONFIRMED)

    with pytest.raises(ValidationError) as caught:
        services.change_arrangement(
            event.reference,
            arrangement_id,
            {"purpose": "   "},
            coordinator_id=COORDINATOR_ID,
            session=db_session,
        )

    assert caught.value.details == {"purpose": ["Must not be blank."]}
