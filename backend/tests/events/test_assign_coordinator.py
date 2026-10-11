"""Unit tests for SCRUM-30 "Assign a coordinator to a submitted event": the assignment.

AC1 assigned a submitted request to the Event Coordinator with the fewest open
requests, lowest user id on a tie (ADR-0018). SCRUM-95 supersedes that: a submitted
request is assigned to nobody and waits for the Event Coordinator Lead to give it to
a coordinator (SCRUM-95 AC1, ADR-0036), so the least-loaded rule and the statuses it
counted are gone from the code. What stays here is the regression guard that nothing
chooses a coordinator on submission, whatever the coordinators are holding.

AC2 — a request has one ``coordinator_id`` and its assignment is written once to the
event history — is still the rule, but submission is no longer where it happens: the
Lead's assignment is, and SCRUM-95 tests it there. On submission the history stays
empty, including when a reference collision is retried.

Runs against ``db_session`` with ``saved_users`` (Event Coordinators 3 and 9, Venue
Staff 4, Event Organiser 7), so a coordinator really is there to be chosen.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.schemas import EventRequestSchema
from app.modules.notifications.models import Notification, NotificationKind
from tests.events.cases import LEAD_ID

pytestmark = pytest.mark.scrum_30

MakeEventRequest = Callable[..., EventRequest]
SubmitValidRequest = Callable[..., EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
HoldRequest = Callable[..., None]
CoordinatorOf = Callable[[int], int | None]


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
# AC1, superseded by SCRUM-95 — a submitted request goes to nobody
# --------------------------------------------------------------------------


@pytest.mark.scrum_39
@pytest.mark.scrum_95
def test_a_submitted_request_is_saved_unassigned_and_only_the_lead_is_told(
    saved_users: list[User],
    saved_leads: list[User],
    submit_valid_request: SubmitValidRequest,
    history_of: HistoryOf,
    coordinator_of: CoordinatorOf,
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Also SCRUM-39's guard: with nobody assigned, not even the organiser is told.

    Event Coordinators 3 and 9 are both there and both free, so until SCRUM-95 this
    request would have gone to coordinator 3. The one thing said about it is each
    Lead's ``request_queued_for_lead`` notice (AC4), which is why nothing is logged as
    a warning: waiting for the Lead is no longer something that needs attention.
    """
    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        submitted = submit_valid_request()

    assert coordinator_of(submitted.id) is None
    assert submitted.status is EventRequestStatus.SUBMITTED
    assert history_of(submitted.id) == []
    notices = db_session.execute(
        select(Notification.recipient_id, Notification.kind).order_by(Notification.recipient_id)
    ).all()
    assert [tuple(notice) for notice in notices] == [
        (LEAD_ID, NotificationKind.REQUEST_QUEUED_FOR_LEAD),
        (12, NotificationKind.REQUEST_QUEUED_FOR_LEAD),
    ]
    assert caplog.records == []


@pytest.mark.scrum_95
@pytest.mark.parametrize(
    ("open_for_3", "open_for_9"),
    [(0, 0), (1, 0), (1, 1), (2, 1), (0, 1)],
    ids=["both-free", "three-is-busier", "busy-tie", "three-is-busier-still", "nine-is-busier"],
)
def test_a_coordinators_load_does_not_decide_who_gets_it(
    saved_users: list[User],
    hold_request: HoldRequest,
    submit_valid_request: SubmitValidRequest,
    coordinator_of: CoordinatorOf,
    open_for_3: int,
    open_for_9: int,
) -> None:
    """The load table ADR-0018 chose by: no arrangement of it assigns anyone now."""
    for _ in range(open_for_3):
        hold_request(3)
    for _ in range(open_for_9):
        hold_request(9)

    submitted = submit_valid_request()

    assert coordinator_of(submitted.id) is None


# --------------------------------------------------------------------------
# AC2 — the assignment is recorded once, and submission is not where it happens
# --------------------------------------------------------------------------


@pytest.mark.scrum_95
def test_submitting_records_nothing_in_the_event_history(
    saved_users: list[User], submit_valid_request: SubmitValidRequest, db_session: Session
) -> None:
    """The Lead's assignment writes the first entry a request gets (SCRUM-95 AC3)."""
    submit_valid_request()

    assert db_session.scalars(select(EventHistoryEntry)).all() == []


@pytest.mark.scrum_95
def test_a_retried_reference_collision_leaves_one_unassigned_request(
    saved_users: list[User],
    save: Callable[..., None],
    make_event_request: MakeEventRequest,
    submit_valid_request: SubmitValidRequest,
    coordinator_of: CoordinatorOf,
    db_session: Session,
) -> None:
    """The rolled-back first attempt leaves behind neither a request nor an entry."""
    save(make_event_request(reference="EVR-AAAAAAAA"))

    submitted = submit_valid_request("EVR-AAAAAAAA", "EVR-BBBBBBBB")

    assert submitted.reference == "EVR-BBBBBBBB"
    assert coordinator_of(submitted.id) is None
    saved = db_session.scalars(select(EventRequest.reference)).all()
    assert sorted(saved) == ["EVR-AAAAAAAA", "EVR-BBBBBBBB"]
    assert db_session.scalars(select(EventHistoryEntry)).all() == []


def test_coordinator_id_is_not_shown_to_clients(make_event_request: MakeEventRequest) -> None:
    dumped = EventRequestSchema().dump(make_event_request(coordinator_id=3))

    assert "coordinator_id" not in dumped
