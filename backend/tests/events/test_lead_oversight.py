"""Unit tests for SCRUM-96 "Lead reassigns events and oversees coordinator assignments".

Task 1, AC3 and AC4: only the Event Coordinator Lead may reassign an event, whichever
coordinator holds it, and the reassignment is still audited with the Lead as its actor.
The refusals SCRUM-87 built stay as they were: an event with no coordinator, an event
that is over, and a move to the coordinator who already holds it.

Runs against ``db_session`` with ``saved_users``, ``saved_leads`` and
``saved_event_request`` (``EVR-AAAAAAAA``, assigned to Event Coordinator 3).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.common.errors import ConflictError
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import (
    ALREADY_ASSIGNED_MESSAGE,
    NOT_ASSIGNED_MESSAGE,
    NOT_REASSIGNABLE_MESSAGE,
    RequestNotReassignableError,
)
from tests.events.cases import LEAD_ID

pytestmark = pytest.mark.scrum_96

Reassign = Callable[[str], Any]
CoordinatorOf = Callable[[int], int | None]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]

NINE = "coordinator9@example.com"


def test_the_lead_reassigns_an_event_they_do_not_coordinate(
    reassign: Reassign, coordinator_of: CoordinatorOf, saved_event_request: EventRequest
) -> None:
    reassign(NINE)

    assert coordinator_of(saved_event_request.id) == 9


def test_the_lead_is_recorded_as_having_reassigned_it(
    reassign: Reassign, history_of: HistoryOf, saved_event_request: EventRequest
) -> None:
    reassign(NINE)

    assert history_of(saved_event_request.id) == [
        (
            EventHistoryKind.COORDINATOR_REASSIGNED,
            LEAD_ID,
            {
                "previous_coordinator_id": 3,
                "previous_coordinator_name": "Coordinator Three",
                "coordinator_id": 9,
                "coordinator_name": "Coordinator Nine",
            },
        )
    ]


def test_the_lead_cannot_reassign_an_event_that_has_no_coordinator(
    reassign: Reassign,
    saved_event_request: EventRequest,
    save: Callable[..., None],
    coordinator_of: CoordinatorOf,
) -> None:
    """Giving an event its first coordinator is SCRUM-95's route, not a reassignment."""
    saved_event_request.coordinator_id = None
    save(saved_event_request)

    with pytest.raises(RequestNotReassignableError) as exc_info:
        reassign(NINE)

    assert exc_info.value.message == NOT_ASSIGNED_MESSAGE
    assert coordinator_of(saved_event_request.id) is None


def test_the_lead_cannot_reassign_an_event_to_the_coordinator_who_holds_it(
    reassign: Reassign, coordinator_of: CoordinatorOf, saved_event_request: EventRequest
) -> None:
    with pytest.raises(ConflictError) as exc_info:
        reassign("coordinator3@example.com")

    assert exc_info.value.message == ALREADY_ASSIGNED_MESSAGE
    assert coordinator_of(saved_event_request.id) == 3


def test_the_lead_cannot_reassign_an_event_that_is_over(
    reassign: Reassign,
    set_status: Callable[[EventRequestStatus], None],
    coordinator_of: CoordinatorOf,
    saved_event_request: EventRequest,
) -> None:
    set_status(EventRequestStatus.COMPLETED)

    with pytest.raises(RequestNotReassignableError) as exc_info:
        reassign(NINE)

    assert exc_info.value.message == NOT_REASSIGNABLE_MESSAGE
    assert coordinator_of(saved_event_request.id) == 3
