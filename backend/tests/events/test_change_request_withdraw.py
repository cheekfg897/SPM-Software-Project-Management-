"""Unit tests for SCRUM-56 "Request a change after submitting my event": withdrawing.

AC8: the event's own Organiser withdraws their Pending change request. It becomes
Withdrawn, with when, and the assigned coordinator is told. A request already decided
(SCRUM-57) or withdrawn can't be withdrawn. The event's row is locked while it happens
(ADR-0126).

AC9: an event cancelled (SCRUM-61) while a change request is Pending closes the
request as Withdrawn, noting the event was cancelled. SCRUM-61 isn't built yet, so the
tests call :func:`withdraw_pending_change_request_on_cancel`, the function its
cancellation is to call inside its own transaction.

Runs against ``db_session`` with ``saved_users``, ``other_organisers`` and
``saved_event_request`` (``EVR-AAAAAAAA``, organiser 7's, assigned to Event Coordinator
3); ``save_change_request`` writes the requests directly.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import Connection, update
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.events.models import ChangeRequestStatus, EventChangeRequest, EventRequest
from app.modules.events.services import (
    CANCELLED_WITHDRAWAL_NOTE,
    CHANGE_REQUEST_NOT_FOUND_MESSAGE,
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    NOT_THE_EVENTS_ORGANISER_MESSAGE,
    ChangeRequestAsShown,
    ChangeRequestNotPendingError,
    NotEventOrganiserError,
    RequestedChange,
    withdraw_pending_change_request_on_cancel,
)
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_56

WithdrawChange = Callable[[int, int], ChangeRequestAsShown]
SaveChangeRequest = Callable[..., EventChangeRequest]
ChangeRequestsOf = Callable[[int], list[EventChangeRequest]]
DetailedNotificationsOf = Callable[[int], list[tuple[Any, ...]]]
OnEventRowLock = Callable[[Callable[[Connection], None]], None]

REFERENCE = "EVR-AAAAAAAA"
ORGANISER_ID = 7
ORGANISER_NAME = "Alice Example"
#: From ``other_organisers``: a colleague in organisation 3 and an organiser of 4.
COLLEAGUE_ID = 8
OTHER_ORGANISATIONS_ORGANISER_ID = 6
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9
#: What ``save_change_request`` saves.
RAISED_AT = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)
REASON = "More partners are coming."

DECIDED_OR_WITHDRAWN = [
    ChangeRequestStatus.APPROVED,
    ChangeRequestStatus.REJECTED,
    ChangeRequestStatus.WITHDRAWN,
]


@pytest.fixture()
def pending(
    saved_users: list[User],
    saved_event_request: EventRequest,
    save_change_request: SaveChangeRequest,
) -> EventChangeRequest:
    """A Pending change request on ``saved_event_request``, for 300 attendees."""
    return save_change_request(saved_event_request)


@pytest.fixture()
def other_event(
    make_event_request: Callable[..., EventRequest], save: Callable[..., None]
) -> EventRequest:
    """Organiser 7's second event, ``EVR-BBBBBBBB``, with the same coordinator."""
    event_request = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=COORDINATOR_ID)
    save(event_request)
    return event_request


# --------------------------------------------------------------------------
# AC8 — the Organiser withdraws their own Pending change request
# --------------------------------------------------------------------------


def test_the_organiser_withdraws_their_pending_request(
    withdraw_change: WithdrawChange,
    pending: EventChangeRequest,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    before = datetime.now(timezone.utc)

    withdraw_change(ORGANISER_ID, pending.id)

    after = datetime.now(timezone.utc)
    [saved] = change_requests_of(saved_event_request.id)
    assert (saved.status, saved.withdrawal_note) == (ChangeRequestStatus.WITHDRAWN, None)
    assert saved.withdrawn_at is not None
    assert before <= saved.withdrawn_at <= after


def test_the_withdrawn_request_is_returned_as_the_record_shows_it(
    withdraw_change: WithdrawChange,
    pending: EventChangeRequest,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    withdrawn = withdraw_change(ORGANISER_ID, pending.id)

    [saved] = change_requests_of(saved_event_request.id)
    assert withdrawn == ChangeRequestAsShown(
        id=pending.id,
        status=ChangeRequestStatus.WITHDRAWN,
        changes=(RequestedChange("expected_attendance", 250, 300),),
        reason=REASON,
        raised_by=ORGANISER_NAME,
        raised_at=RAISED_AT,
        withdrawn_at=saved.withdrawn_at,
        withdrawal_note=None,
    )


def test_the_assigned_coordinator_is_told_and_nobody_else(
    withdraw_change: WithdrawChange,
    pending: EventChangeRequest,
    other_organisers: list[User],
    detailed_notifications_of: DetailedNotificationsOf,
) -> None:
    withdraw_change(ORGANISER_ID, pending.id)

    assert detailed_notifications_of(COORDINATOR_ID) == [
        (REFERENCE, NotificationKind.CHANGE_REQUEST_WITHDRAWN, None)
    ]
    for user_id in (OTHER_COORDINATOR_ID, ORGANISER_ID, COLLEAGUE_ID):
        assert detailed_notifications_of(user_id) == []


def test_with_no_coordinator_assigned_the_withdrawal_is_still_saved_and_logged(
    withdraw_change: WithdrawChange,
    pending: EventChangeRequest,
    saved_event_request: EventRequest,
    save: Callable[..., None],
    change_requests_of: ChangeRequestsOf,
    detailed_notifications_of: DetailedNotificationsOf,
    caplog: pytest.LogCaptureFixture,
) -> None:
    saved_event_request.coordinator_id = None
    save(saved_event_request)

    withdraw_change(ORGANISER_ID, pending.id)

    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is ChangeRequestStatus.WITHDRAWN
    assert detailed_notifications_of(COORDINATOR_ID) == []
    assert f"event_request_unassigned reference={REFERENCE}" in caplog.text


@pytest.mark.parametrize("status", DECIDED_OR_WITHDRAWN, ids=lambda status: status.value)
def test_a_request_no_longer_pending_cannot_be_withdrawn(
    withdraw_change: WithdrawChange,
    saved_users: list[User],
    saved_event_request: EventRequest,
    save_change_request: SaveChangeRequest,
    change_requests_of: ChangeRequestsOf,
    detailed_notifications_of: DetailedNotificationsOf,
    status: ChangeRequestStatus,
) -> None:
    decided = save_change_request(saved_event_request, status)

    with pytest.raises(ChangeRequestNotPendingError) as exc_info:
        withdraw_change(ORGANISER_ID, decided.id)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "change_request_not_pending")
    assert refused.message == (
        f"Only a pending change request can be withdrawn; this one is {status.value}."
    )
    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is status
    assert detailed_notifications_of(COORDINATOR_ID) == []


def test_a_colleague_in_the_same_organisation_is_refused(
    withdraw_change: WithdrawChange,
    pending: EventChangeRequest,
    other_organisers: list[User],
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    with pytest.raises(NotEventOrganiserError) as exc_info:
        withdraw_change(COLLEAGUE_ID, pending.id)

    assert exc_info.value.message == NOT_THE_EVENTS_ORGANISER_MESSAGE
    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is ChangeRequestStatus.PENDING


def test_an_organiser_of_another_organisation_finds_no_such_event(
    withdraw_change: WithdrawChange, pending: EventChangeRequest, other_organisers: list[User]
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        withdraw_change(OTHER_ORGANISATIONS_ORGANISER_ID, pending.id)

    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE


def test_an_unknown_change_request_is_not_found(
    withdraw_change: WithdrawChange, pending: EventChangeRequest
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        withdraw_change(ORGANISER_ID, pending.id + 100)

    assert exc_info.value.message == CHANGE_REQUEST_NOT_FOUND_MESSAGE


def test_another_events_change_request_is_not_found_through_this_event(
    withdraw_change: WithdrawChange,
    saved_users: list[User],
    saved_event_request: EventRequest,
    other_event: EventRequest,
    save_change_request: SaveChangeRequest,
    change_requests_of: ChangeRequestsOf,
) -> None:
    others = save_change_request(other_event)

    with pytest.raises(NotFoundError) as exc_info:
        withdraw_change(ORGANISER_ID, others.id)

    assert exc_info.value.message == CHANGE_REQUEST_NOT_FOUND_MESSAGE
    [saved] = change_requests_of(other_event.id)
    assert saved.status is ChangeRequestStatus.PENDING


def test_a_request_decided_while_waiting_for_the_lock_is_not_withdrawn(
    withdraw_change: WithdrawChange,
    pending: EventChangeRequest,
    on_event_row_lock: OnEventRowLock,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
    db_session: Session,
) -> None:
    """ADR-0126: the coordinator's decision committed first, so it stands.

    Nothing of the request is held in the session beforehand, as in a real request, so
    only the lock decides whether the decision is seen.
    """
    change_request_id = pending.id
    db_session.expire_all()
    approved = (
        update(EventChangeRequest)
        .where(EventChangeRequest.id == change_request_id)
        .values(status=ChangeRequestStatus.APPROVED)
    )
    on_event_row_lock(lambda connection: connection.execute(approved))

    with pytest.raises(ChangeRequestNotPendingError):
        withdraw_change(ORGANISER_ID, change_request_id)

    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is ChangeRequestStatus.APPROVED


# --------------------------------------------------------------------------
# AC9 — cancelling the event withdraws its Pending request (called by SCRUM-61)
# --------------------------------------------------------------------------


def test_cancelling_withdraws_the_pending_request_noting_the_event_was_cancelled(
    pending: EventChangeRequest,
    saved_event_request: EventRequest,
    db_session: Session,
    change_requests_of: ChangeRequestsOf,
) -> None:
    before = datetime.now(timezone.utc)

    withdraw_pending_change_request_on_cancel(saved_event_request.id, session=db_session)
    db_session.commit()

    after = datetime.now(timezone.utc)
    [saved] = change_requests_of(saved_event_request.id)
    assert (saved.status, saved.withdrawal_note) == (
        ChangeRequestStatus.WITHDRAWN,
        CANCELLED_WITHDRAWAL_NOTE,
    )
    assert "cancelled" in CANCELLED_WITHDRAWAL_NOTE
    assert saved.withdrawn_at is not None
    assert before <= saved.withdrawn_at <= after


def test_cancelling_leaves_the_commit_to_the_cancellation(
    pending: EventChangeRequest,
    saved_event_request: EventRequest,
    db_session: Session,
    change_requests_of: ChangeRequestsOf,
) -> None:
    withdraw_pending_change_request_on_cancel(saved_event_request.id, session=db_session)
    db_session.rollback()

    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is ChangeRequestStatus.PENDING


def test_cancelling_tells_nobody(
    pending: EventChangeRequest,
    saved_event_request: EventRequest,
    db_session: Session,
    detailed_notifications_of: DetailedNotificationsOf,
) -> None:
    withdraw_pending_change_request_on_cancel(saved_event_request.id, session=db_session)
    db_session.commit()

    assert detailed_notifications_of(COORDINATOR_ID) == []


@pytest.mark.parametrize("status", DECIDED_OR_WITHDRAWN, ids=lambda status: status.value)
def test_cancelling_leaves_a_request_no_longer_pending_as_it_is(
    saved_users: list[User],
    saved_event_request: EventRequest,
    save_change_request: SaveChangeRequest,
    db_session: Session,
    change_requests_of: ChangeRequestsOf,
    status: ChangeRequestStatus,
) -> None:
    save_change_request(saved_event_request, status)

    withdraw_pending_change_request_on_cancel(saved_event_request.id, session=db_session)
    db_session.commit()

    [saved] = change_requests_of(saved_event_request.id)
    assert (saved.status, saved.withdrawal_note) == (status, None)


def test_cancelling_one_event_leaves_another_events_request_pending(
    saved_event_request: EventRequest,
    other_event: EventRequest,
    save_change_request: SaveChangeRequest,
    db_session: Session,
    change_requests_of: ChangeRequestsOf,
) -> None:
    # Only the other event has a Pending request, so a lookup that ignored the event
    # would find it.
    save_change_request(other_event)

    withdraw_pending_change_request_on_cancel(saved_event_request.id, session=db_session)
    db_session.commit()

    [others] = change_requests_of(other_event.id)
    assert others.status is ChangeRequestStatus.PENDING
