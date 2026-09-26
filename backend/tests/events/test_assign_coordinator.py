"""Unit tests for SCRUM-30 "Assign a coordinator to a submitted event": the assignment.

AC1: a submitted request is assigned to exactly one Event Coordinator. ADR-0018 sets
the rule: the coordinator with the fewest open (``submitted`` or ``under_review``)
requests, lowest user id on a tie; with no Event Coordinator at all, the request is
saved unassigned and a warning is logged. AC2: a request has one ``coordinator_id``,
and the assignment is written once to the event history in the same commit, so a
retried reference collision leaves exactly one.

Runs against ``db_session`` with ``saved_users`` (Event Coordinators 3 and 9, Venue
Staff 4, Event Organiser 7), so the role filter, the grouped count and the tie-break
are real SQL.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

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
from app.modules.events.schemas import EventRequestSchema
from app.modules.notifications.models import Notification

pytestmark = pytest.mark.scrum_30

MakeEventRequest = Callable[..., EventRequest]
SubmitValidRequest = Callable[..., EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
HoldRequest = Callable[..., None]
CoordinatorOf = Callable[[int], int | None]

#: Who each status sends the next request to, when coordinator 3 already holds one
#: request in that status and coordinator 9 holds none (ADR-0018).
NEXT_ASSIGNEE_BY_STATUS = [
    (EventRequestStatus.DRAFT, 3),
    (EventRequestStatus.SUBMITTED, 9),
    (EventRequestStatus.UNDER_REVIEW, 9),
    (EventRequestStatus.AWAITING_CLARIFICATION, 9),
    (EventRequestStatus.APPROVED, 9),
    (EventRequestStatus.CONFIRMED, 3),
    (EventRequestStatus.COMPLETED, 3),
    (EventRequestStatus.CANCELLED, 3),
    (EventRequestStatus.REJECTED, 3),
]


@pytest.fixture()
def hold_request(save: Callable[..., None], make_event_request: MakeEventRequest) -> HoldRequest:
    """Save a request already assigned to a coordinator; ``submitted`` by default."""
    counter = {"n": 0}

    def _hold(
        coordinator_id: int, status: EventRequestStatus = EventRequestStatus.SUBMITTED
    ) -> None:
        counter["n"] += 1
        save(
            make_event_request(
                reference=f"EVR-LOAD{counter['n']:04d}",
                status=status,
                coordinator_id=coordinator_id,
            )
        )

    return _hold


# --------------------------------------------------------------------------
# AC1 — a submitted request goes to one Event Coordinator: the least loaded
# --------------------------------------------------------------------------


def test_a_submitted_request_is_assigned_to_an_event_coordinator(
    saved_users: list[User],
    submit_valid_request: SubmitValidRequest,
    coordinator_of: CoordinatorOf,
) -> None:
    submitted = submit_valid_request()

    assert coordinator_of(submitted.id) == 3
    assert submitted.status is EventRequestStatus.SUBMITTED


@pytest.mark.parametrize(
    ("open_for_3", "open_for_9", "expected"),
    [(0, 0, 3), (1, 0, 9), (1, 1, 3), (2, 1, 9), (0, 1, 3)],
    ids=["tie-lowest-id", "three-is-busier", "busy-tie", "three-is-busier-still", "nine-is-busier"],
)
def test_the_coordinator_with_the_fewest_open_requests_is_assigned(
    saved_users: list[User],
    hold_request: HoldRequest,
    submit_valid_request: SubmitValidRequest,
    coordinator_of: CoordinatorOf,
    open_for_3: int,
    open_for_9: int,
    expected: int,
) -> None:
    # In "busy-tie", Venue Staff 4 and Organiser 7 hold no requests and would win if
    # candidates weren't limited to Event Coordinators.
    for _ in range(open_for_3):
        hold_request(3)
    for _ in range(open_for_9):
        hold_request(9)

    submitted = submit_valid_request()

    assert coordinator_of(submitted.id) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    NEXT_ASSIGNEE_BY_STATUS,
    ids=[status.value for status, _ in NEXT_ASSIGNEE_BY_STATUS],
)
def test_only_open_statuses_count_towards_a_coordinators_load(
    saved_users: list[User],
    hold_request: HoldRequest,
    submit_valid_request: SubmitValidRequest,
    coordinator_of: CoordinatorOf,
    status: EventRequestStatus,
    expected: int,
) -> None:
    hold_request(3, status)

    submitted = submit_valid_request()

    assert coordinator_of(submitted.id) == expected


@pytest.mark.scrum_39
def test_with_no_event_coordinator_the_request_is_saved_unassigned_and_logged(
    save: Callable[..., None],
    make_user: Callable[..., User],
    submit_valid_request: SubmitValidRequest,
    history_of: HistoryOf,
    coordinator_of: CoordinatorOf,
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Also SCRUM-39's guard: with nobody assigned, not even the organiser is told."""
    save(make_user(role=Role.EVENT_ORGANISER, user_id=7, organisation_id=3))

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        submitted = submit_valid_request()

    assert coordinator_of(submitted.id) is None
    assert submitted.status is EventRequestStatus.SUBMITTED
    assert history_of(submitted.id) == []
    assert db_session.scalars(select(Notification)).all() == []
    assert [record.getMessage() for record in caplog.records] == [
        "event_request_unassigned reference=EVR-AAAAAAAA"
    ]


# --------------------------------------------------------------------------
# AC2 — one assignment, recorded once in the event history
# --------------------------------------------------------------------------


def test_assignment_is_recorded_once_in_the_event_history(
    saved_users: list[User],
    submit_valid_request: SubmitValidRequest,
    history_of: HistoryOf,
    db_session: Session,
) -> None:
    before = datetime.now(timezone.utc)

    submitted = submit_valid_request()

    after = datetime.now(timezone.utc)
    assert history_of(submitted.id) == [
        (EventHistoryKind.COORDINATOR_ASSIGNED, None, {"coordinator_id": 3})
    ]
    entry = db_session.scalars(select(EventHistoryEntry)).one()
    assert before <= entry.occurred_at <= after


def test_a_reference_collision_leaves_one_assignment_for_the_saved_request(
    saved_users: list[User],
    save: Callable[..., None],
    make_event_request: MakeEventRequest,
    submit_valid_request: SubmitValidRequest,
    history_of: HistoryOf,
    coordinator_of: CoordinatorOf,
    db_session: Session,
) -> None:
    save(make_event_request(reference="EVR-AAAAAAAA"))

    submitted = submit_valid_request("EVR-AAAAAAAA", "EVR-BBBBBBBB")

    assert submitted.reference == "EVR-BBBBBBBB"
    assert coordinator_of(submitted.id) == 3
    assert history_of(submitted.id) == [
        (EventHistoryKind.COORDINATOR_ASSIGNED, None, {"coordinator_id": 3})
    ]
    # The rolled-back first attempt left no entry behind.
    assert len(db_session.scalars(select(EventHistoryEntry)).all()) == 1


def test_coordinator_id_is_not_shown_to_clients(make_event_request: MakeEventRequest) -> None:
    dumped = EventRequestSchema().dump(make_event_request(coordinator_id=3))

    assert "coordinator_id" not in dumped
