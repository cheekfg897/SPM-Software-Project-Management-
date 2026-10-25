"""Unit tests for SCRUM-49 AC12: a rejection during planning is final as a decision.

AC12: once the assigned coordinator rejects an event during planning (AC9), no new
decision can be recorded on it through SCRUM-31, even if it never had a venue or
equipment request; to go ahead, the organiser submits a new event request (SCRUM-19).
A rejection recorded through SCRUM-31 itself can still be changed (SCRUM-31 AC6), so
the planning rejection is told apart by a marker on its decision entry (ADR-0106).

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, organiser 7, assigned to Event Coordinator 3).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import (
    DecisionLockedError,
    decide_event_request,
    reject_event_during_planning,
)
from app.modules.notifications.services import NotificationKind
from tests.events.cases import AddLine, decisions_in

pytestmark = pytest.mark.scrum_49

Decide = Callable[..., EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
ReloadEventRequest = Callable[[int], EventRequest]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]

REFERENCE = "EVR-AAAAAAAA"
OTHER_REFERENCE = "EVR-BBBBBBBB"
COORDINATOR_ID = 3
ORGANISER_ID = 7
REASON = "No venue large enough is free that week."
CHANGE_REASON = "A larger hall came free."
PLANNING_STATUSES = [EventRequestStatus.APPROVED, EventRequestStatus.SAFETY_REVIEW]
PLANNING_REJECTION_FINAL = (
    "The decision can't be changed once the event has been rejected during planning. "
    "To go ahead, the organiser submits a new event request."
)


def _move_to(
    event_request: EventRequest, status: EventRequestStatus, save: Callable[..., None]
) -> None:
    event_request.status = status
    save(event_request)


def _reject_during_planning(session: Session, reference: str = REFERENCE) -> None:
    reject_event_during_planning(COORDINATOR_ID, reference, {"reason": REASON}, session=session)


def _assert_refused_as_final(decide: Callable[[], Any]) -> None:
    """Try a new decision and check it is refused as final (AC12)."""
    with pytest.raises(DecisionLockedError) as exc_info:
        decide()

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "decision_locked")
    assert refused.message == PLANNING_REJECTION_FINAL


# --------------------------------------------------------------------------
# AC12 — no new decision through SCRUM-31 once rejected during planning
# --------------------------------------------------------------------------


@pytest.mark.parametrize("planning_status", PLANNING_STATUSES, ids=lambda status: status.value)
@pytest.mark.parametrize("outcome", ["approved", "rejected"])
def test_an_event_rejected_during_planning_cannot_be_decided_again(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    save: Callable[..., None],
    decide: Decide,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    detailed_notifications_of: NotificationsOf,
    planning_status: EventRequestStatus,
    outcome: str,
) -> None:
    """Even with no venue or equipment request ever raised (AC12)."""
    _move_to(saved_event_request, planning_status, save)
    _reject_during_planning(db_session)

    _assert_refused_as_final(lambda: decide(COORDINATOR_ID, outcome, CHANGE_REASON))

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.REJECTED
    assert len(decisions_in(history_of(saved_event_request.id))) == 1
    assert detailed_notifications_of(ORGANISER_ID) == [
        (REFERENCE, NotificationKind.EVENT_REQUEST_REJECTED, REASON)
    ]


def test_the_refusal_comes_before_the_body_is_read(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    save: Callable[..., None],
) -> None:
    """As every lock is checked: the event, its status, the lock, then the body."""
    _move_to(saved_event_request, EventRequestStatus.APPROVED, save)
    _reject_during_planning(db_session)

    _assert_refused_as_final(lambda: decide_event_request(COORDINATOR_ID, REFERENCE, {}))


def test_the_refusal_names_the_planning_rejection_when_equipment_was_requested(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    save: Callable[..., None],
    add_line: AddLine,
    decide: Decide,
) -> None:
    """The rejection is why, not the equipment request it closed (SCRUM-31 AC7)."""
    _move_to(saved_event_request, EventRequestStatus.APPROVED, save)
    add_line(None)
    _reject_during_planning(db_session)

    _assert_refused_as_final(lambda: decide(COORDINATOR_ID, "approved", CHANGE_REASON))


def test_the_planning_rejection_is_marked_on_its_decision_entry(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    save: Callable[..., None],
    history_of: HistoryOf,
) -> None:
    _move_to(saved_event_request, EventRequestStatus.APPROVED, save)

    _reject_during_planning(db_session)

    assert decisions_in(history_of(saved_event_request.id)) == [
        {"outcome": "rejected", "reason": REASON, "during_planning": True}
    ]


# --------------------------------------------------------------------------
# Decoys: a rejection through SCRUM-31 can still be changed (SCRUM-31 AC6)
# --------------------------------------------------------------------------


def test_an_approval_changed_to_a_rejection_through_scrum_31_can_be_changed_again(
    decide: Decide, reload_event_request: ReloadEventRequest, saved_event_request: EventRequest
) -> None:
    """Approved then rejected, nothing arranged: looks like a planning rejection."""
    decide(COORDINATOR_ID, "approved")
    decide(COORDINATOR_ID, "rejected", REASON)

    decide(COORDINATOR_ID, "approved", CHANGE_REASON)

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.APPROVED


def test_another_events_planning_rejection_does_not_lock_this_one(
    db_session: Session,
    decide: Decide,
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    other = make_event_request(
        reference=OTHER_REFERENCE, status=EventRequestStatus.APPROVED, coordinator_id=3
    )
    save(other)
    _reject_during_planning(db_session, OTHER_REFERENCE)
    decide(COORDINATOR_ID, "rejected", REASON)

    decide(COORDINATOR_ID, "approved", CHANGE_REASON)

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.APPROVED
