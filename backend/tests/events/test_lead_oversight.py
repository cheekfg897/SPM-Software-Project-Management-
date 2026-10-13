"""Unit tests for SCRUM-96 "Lead reassigns events and oversees coordinator assignments".

Task 1, AC3 and AC4: only the Event Coordinator Lead may reassign an event, whichever
coordinator holds it, and the reassignment is still audited with the Lead as its actor.
The refusals SCRUM-87 built stay as they were: an event with no coordinator, an event
that is over, and a move to the coordinator who already holds it.

Task 2, AC5: the coordinator who loses the event is told, as well as the new coordinator
and the organiser. AC1 and AC2: the Lead's two lists, every active event and each
coordinator's active events.

Runs against ``db_session`` with ``saved_users``, ``saved_leads`` and
``saved_event_request`` (``EVR-AAAAAAAA``, assigned to Event Coordinator 3).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import (
    ACTIVE_STATUSES,
    ALREADY_ASSIGNED_MESSAGE,
    NOT_ASSIGNED_MESSAGE,
    NOT_REASSIGNABLE_MESSAGE,
    RequestNotReassignableError,
    list_active_requests,
    list_requests_for_each_coordinator,
)
from app.modules.notifications.models import Notification
from app.modules.notifications.services import NotificationKind
from tests.events.cases import LEAD_ID

pytestmark = pytest.mark.scrum_96

Reassign = Callable[[str], Any]
CoordinatorOf = Callable[[int], int | None]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]
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


# --------------------------------------------------------------------------
# AC5 — the coordinator who loses the event is told
# --------------------------------------------------------------------------


def test_the_previous_coordinator_is_told_the_event_is_no_longer_theirs(
    reassign: Reassign, notifications_of: NotificationsOf, saved_event_request: EventRequest
) -> None:
    reassign(NINE)

    assert notifications_of(3) == [
        (
            saved_event_request.id,
            "EVR-AAAAAAAA",
            "Partner Summit",
            NotificationKind.REQUEST_ASSIGNED,
            None,
        )
    ]


def test_a_reassignment_tells_exactly_the_new_coordinator_the_organiser_and_the_previous_one(
    reassign: Reassign, db_session: Session
) -> None:
    reassign(NINE)

    notices = db_session.scalars(select(Notification)).all()
    assert sorted((notice.recipient_id, notice.kind.value) for notice in notices) == [
        (3, "request_assigned"),
        (7, "request_assigned"),
        (9, "coordinator_assigned"),
    ]


# --------------------------------------------------------------------------
# AC1 — every active event, with its coordinator and status
# --------------------------------------------------------------------------

ONE_EVENT_IN_EACH_STATUS = {
    status: f"EVR-{index:08d}" for index, status in enumerate(EventRequestStatus)
}
INACTIVE_STATUSES = set(EventRequestStatus) - ACTIVE_STATUSES


@pytest.fixture()
def one_event_in_each_status(
    saved_users: list[Any],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
) -> dict[EventRequestStatus, EventRequest]:
    """Coordinator 3 holds one saved event for every status, by status."""
    events = {}
    for status, reference in ONE_EVENT_IN_EACH_STATUS.items():
        events[status] = make_event_request(reference=reference, status=status, coordinator_id=3)
    save(*events.values())
    return events


def test_the_active_statuses_are_those_from_submission_until_the_event_is_over() -> None:
    assert {
        EventRequestStatus.SUBMITTED,
        EventRequestStatus.UNDER_REVIEW,
        EventRequestStatus.AWAITING_CLARIFICATION,
        EventRequestStatus.APPROVED,
        EventRequestStatus.CONFIRMED,
    } == ACTIVE_STATUSES


def test_the_active_list_has_the_five_active_statuses_and_no_other(
    one_event_in_each_status: dict[EventRequestStatus, EventRequest],
) -> None:
    listed = {row.event_request.id for row in list_active_requests()}

    expected = {one_event_in_each_status[status].id for status in ACTIVE_STATUSES}
    assert listed == expected


@pytest.mark.parametrize("status", sorted(INACTIVE_STATUSES, key=lambda status: status.value))
def test_the_active_list_leaves_out_an_event_that_is_not_active(
    one_event_in_each_status: dict[EventRequestStatus, EventRequest], status: EventRequestStatus
) -> None:
    left_out = one_event_in_each_status[status].id

    assert left_out not in {row.event_request.id for row in list_active_requests()}


def test_the_active_list_names_each_events_coordinator_and_status(
    saved_users: list[Any],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
) -> None:
    held = make_event_request(reference="EVR-HELD0001", coordinator_id=9)
    waiting = make_event_request(reference="EVR-WAIT0001", coordinator_id=None)
    save(held, waiting)

    shown = {
        row.event_request.reference: (row.event_request.status, row.coordinator_name)
        for row in list_active_requests()
    }

    assert shown == {
        "EVR-HELD0001": (EventRequestStatus.SUBMITTED, "Coordinator Nine"),
        "EVR-WAIT0001": (EventRequestStatus.SUBMITTED, None),
    }


def test_the_active_list_is_newest_first(
    saved_users: list[Any],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
) -> None:
    older = make_event_request(reference="EVR-OLDER001", coordinator_id=3)
    newer = make_event_request(reference="EVR-NEWER001", coordinator_id=3)
    save(older)
    save(newer)

    references = [row.event_request.reference for row in list_active_requests()]

    assert references == ["EVR-NEWER001", "EVR-OLDER001"]


# --------------------------------------------------------------------------
# AC2 — each coordinator's active events
# --------------------------------------------------------------------------


def test_each_coordinator_with_active_events_is_listed_with_their_events(
    saved_users: list[Any],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
) -> None:
    save(
        make_event_request(reference="EVR-THREE001", coordinator_id=3),
        make_event_request(reference="EVR-THREE002", coordinator_id=3),
        make_event_request(reference="EVR-NINE0001", coordinator_id=9),
    )

    workloads = list_requests_for_each_coordinator()

    shown = [
        (w.coordinator_name, sorted(event.reference for event in w.assigned)) for w in workloads
    ]
    assert shown == [
        ("Coordinator Nine", ["EVR-NINE0001"]),
        ("Coordinator Three", ["EVR-THREE001", "EVR-THREE002"]),
    ]


def test_a_coordinator_with_no_active_event_is_left_out(
    one_event_in_each_status: dict[EventRequestStatus, EventRequest],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
) -> None:
    """Coordinator 9 holds only a completed event, so has nothing to supervise."""
    save(
        make_event_request(
            reference="EVR-NINE0001", status=EventRequestStatus.COMPLETED, coordinator_id=9
        )
    )

    coordinator_ids = [w.coordinator_id for w in list_requests_for_each_coordinator()]

    assert coordinator_ids == [3]


def test_an_inactive_event_is_not_counted_in_a_coordinators_events(
    one_event_in_each_status: dict[EventRequestStatus, EventRequest],
) -> None:
    (workload,) = list_requests_for_each_coordinator()

    assert {event.id for event in workload.assigned} == {
        one_event_in_each_status[status].id for status in ACTIVE_STATUSES
    }


def test_an_event_waiting_for_the_lead_is_in_nobodys_workload(
    saved_users: list[Any],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
) -> None:
    save(make_event_request(coordinator_id=None))

    assert list_requests_for_each_coordinator() == []
