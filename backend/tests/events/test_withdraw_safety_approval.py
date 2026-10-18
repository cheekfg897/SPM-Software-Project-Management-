"""Unit tests for withdrawing an event's safety approval, whatever withdrew it.

A replacement venue (SCRUM-92 AC10), a significant change (SCRUM-33 AC7), a changed
equipment line (SCRUM-37 AC4), equipment taken out of service (SCRUM-47 AC5) and a
revised equipment outcome (SCRUM-48 AC7) all mean the event must pass a new safety
check. The withdrawal is a ``safety_approval_withdrawn`` entry by whoever made the
change, with what the change was. Wherever the event was, it ends up Approved, the only
status it can be sent to Safety Review from (ADR-0087). An event with no approval is
left as it is, and nothing is written.

Runs against ``db_session``, so ``has_safety_approval`` reads the saved history.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import has_safety_approval, withdraw_safety_approval

pytestmark = [
    pytest.mark.scrum_33,
    pytest.mark.scrum_37,
    pytest.mark.scrum_47,
    pytest.mark.scrum_48,
    pytest.mark.scrum_92,
]

ApprovedForSafety = Callable[[EventRequestStatus], EventRequest]
WithdrawalsOf = Callable[[int], list[tuple[int | None, dict[str, Any] | None]]]

#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
#: What the caller says the change was; the function stores it as given.
DETAILS = {"significant_fields": ["expected_attendance"]}
#: Where an event with an approval can be when it is withdrawn.
WITHDRAWN_FROM = [
    EventRequestStatus.SAFETY_REVIEW,
    EventRequestStatus.CONFIRMED,
    EventRequestStatus.APPROVED,
]
#: Every other status, built from the enum so a status added later is covered too.
#: A completed or cancelled event may still carry the approval it was confirmed with.
LEFT_WHERE_IT_IS = [status for status in EventRequestStatus if status not in WITHDRAWN_FROM]


def _withdraw(event: EventRequest, session: Session) -> None:
    withdraw_safety_approval(event.id, actor_id=COORDINATOR_ID, details=DETAILS, session=session)
    session.commit()


@pytest.mark.parametrize("status", WITHDRAWN_FROM)
def test_an_approved_event_ends_up_approved_for_a_new_safety_check(
    db_session: Session,
    approved_for_safety: ApprovedForSafety,
    safety_withdrawals_of: WithdrawalsOf,
    status: EventRequestStatus,
) -> None:
    event = approved_for_safety(status)

    _withdraw(event, db_session)

    assert has_safety_approval(event.id, session=db_session) is False
    assert safety_withdrawals_of(event.id) == [(COORDINATOR_ID, DETAILS)]
    db_session.expire_all()
    assert event.status is EventRequestStatus.APPROVED


@pytest.mark.parametrize("status", LEFT_WHERE_IT_IS)
def test_an_event_past_planning_loses_the_approval_but_keeps_its_status(
    db_session: Session, approved_for_safety: ApprovedForSafety, status: EventRequestStatus
) -> None:
    event = approved_for_safety(status)

    _withdraw(event, db_session)

    assert has_safety_approval(event.id, session=db_session) is False
    db_session.expire_all()
    assert event.status is status


def test_an_event_without_an_approval_keeps_its_status(
    db_session: Session,
    saved_event_request: EventRequest,
    save: Callable[..., None],
    safety_withdrawals_of: WithdrawalsOf,
) -> None:
    saved_event_request.status = EventRequestStatus.CONFIRMED
    save(saved_event_request)

    _withdraw(saved_event_request, db_session)

    assert safety_withdrawals_of(saved_event_request.id) == []
    db_session.expire_all()
    assert saved_event_request.status is EventRequestStatus.CONFIRMED
