"""Unit tests for SCRUM-56 "Request a change after submitting my event": raising one.

The event's own Organiser raises a change request against their event, saying what
should change and why (AC1). Only the event's date, times, expected attendance, venue
and equipment requirements and programme information can be asked for (AC2). The event
itself is left as it is (AC3); the request is saved Pending (AC4) and the assigned
coordinator is told (AC5). It is refused for a Draft, Completed, Cancelled or Rejected
event, with nothing said about what should change or why, and for anyone but the
event's own Organiser, saying which (AC6). An event has at most one Pending request, and
the database enforces it (AC7). The event's row is locked while the request is raised
(ADR-0126). What the record shows is in ``test_change_request_record.py``.

Runs against ``db_session`` with ``saved_users``, ``other_organisers`` and
``saved_event_request`` (``EVR-AAAAAAAA``, organiser 7's, filed under client
organisation 3, proposed 2026-10-15 09:00-17:00 for 250, assigned to Event Coordinator
3); ``today`` is 2026-09-15. The integrity-error test uses ``mock_session``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Connection, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.events.models import (
    ChangeRequestStatus,
    EventChangeRequest,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.schemas import CHANGE_REASON_REQUIRED_MESSAGE
from app.modules.events.services import (
    CHANGE_REQUEST_ALREADY_PENDING_MESSAGE,
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    NOT_THE_EVENTS_ORGANISER_MESSAGE,
    NOTHING_TO_CHANGE_MESSAGE,
    ChangeRequestAsShown,
    ChangeRequestNotAllowedError,
    NotEventOrganiserError,
    OrganiserWithoutOrganisationError,
    RequestedChange,
    raise_change_request,
)
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_56

RaiseChange = Callable[[int, Any], ChangeRequestAsShown]
ChangeRequestsOf = Callable[[int], list[EventChangeRequest]]
SaveChangeRequest = Callable[..., EventChangeRequest]
SetStatus = Callable[[EventRequestStatus], None]
ReloadEventRequest = Callable[[int], EventRequest]
DetailedNotificationsOf = Callable[[int], list[tuple[Any, ...]]]
OnEventRowLock = Callable[[Callable[[Connection], None]], None]

REFERENCE = "EVR-AAAAAAAA"
ORGANISER_ID = 7
ORGANISER_NAME = "Alice Example"
#: From ``other_organisers``: a colleague in organisation 3, an organiser of
#: organisation 4, and one linked to no organisation.
COLLEAGUE_ID = 8
OTHER_ORGANISATIONS_ORGANISER_ID = 6
UNLINKED_ORGANISER_ID = 10
#: The event's assigned coordinator, and another one who must hear nothing.
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9

REASON = "Fifty more partners have confirmed."
MORE_ATTENDEES = {"expected_attendance": 300, "reason": REASON}

#: SCRUM-56 AC1: every status from Submitted to Confirmed.
RAISABLE_STATUSES = [
    EventRequestStatus.SUBMITTED,
    EventRequestStatus.UNDER_REVIEW,
    EventRequestStatus.AWAITING_CLARIFICATION,
    EventRequestStatus.APPROVED,
    EventRequestStatus.SAFETY_REVIEW,
    EventRequestStatus.CONFIRMED,
]
#: SCRUM-56 AC6: the four statuses either side of that range.
REFUSED_STATUSES = [
    EventRequestStatus.DRAFT,
    EventRequestStatus.COMPLETED,
    EventRequestStatus.CANCELLED,
    EventRequestStatus.REJECTED,
]


def _assert_nothing_raised(change_requests_of: ChangeRequestsOf, event_id: int) -> None:
    assert change_requests_of(event_id) == []


# --------------------------------------------------------------------------
# AC1 — the Organiser raises a change request from Submitted to Confirmed
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", RAISABLE_STATUSES, ids=lambda status: status.value)
def test_the_organiser_raises_a_change_request_in_each_status_up_to_confirmed(
    raise_change: RaiseChange,
    set_status: SetStatus,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    raise_change(ORGANISER_ID, MORE_ATTENDEES)

    [saved] = change_requests_of(saved_event_request.id)
    assert (saved.status, saved.requested_by, saved.reason) == (
        ChangeRequestStatus.PENDING,
        ORGANISER_ID,
        REASON,
    )


def test_the_raised_request_is_returned_as_the_record_shows_it(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    before = datetime.now(timezone.utc)

    raised = raise_change(ORGANISER_ID, MORE_ATTENDEES)

    after = datetime.now(timezone.utc)
    [saved] = change_requests_of(saved_event_request.id)
    assert raised == ChangeRequestAsShown(
        id=saved.id,
        status=ChangeRequestStatus.PENDING,
        changes=(RequestedChange("expected_attendance", 250, 300),),
        reason=REASON,
        raised_by=ORGANISER_NAME,
        raised_at=saved.raised_at,
        withdrawn_at=None,
        withdrawal_note=None,
    )
    assert before <= saved.raised_at <= after


def test_the_reason_is_trimmed(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    raise_change(ORGANISER_ID, {"expected_attendance": 300, "reason": f"  {REASON}  "})

    [saved] = change_requests_of(saved_event_request.id)
    assert saved.reason == REASON


# --------------------------------------------------------------------------
# AC2 — the fields that can be asked for, each with its value when raised
# --------------------------------------------------------------------------


def test_every_requestable_field_is_saved_with_its_value_when_raised(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
    save: Callable[..., None],
    db_session: Session,
) -> None:
    saved_event_request.venue_requirements = "Main hall"
    saved_event_request.equipment_requirements = "Two projectors"
    saved_event_request.programme_notes = "Keynote at 09:30"
    # With no coordinator there is no notice, whose own commit would hide a missing one.
    saved_event_request.coordinator_id = None
    save(saved_event_request)
    payload = {
        "proposed_date": "2026-10-20",
        "end_date": "2026-10-21",
        "start_time": "10:00",
        "end_time": "02:00",
        "expected_attendance": 300,
        "venue_requirements": "Main hall and two breakout rooms",
        "equipment_requirements": "Three projectors",
        "programme_notes": "Keynote at 10:30",
        "reason": REASON,
    }

    raise_change(ORGANISER_ID, payload)
    # Only what was committed survives this, so the read below proves it was saved.
    db_session.rollback()

    [saved] = change_requests_of(saved_event_request.id)
    assert saved.requested_values == {
        "proposed_date": "2026-10-20",
        "end_date": "2026-10-21",
        "start_time": "10:00:00",
        "end_time": "02:00:00",
        "expected_attendance": 300,
        "venue_requirements": "Main hall and two breakout rooms",
        "equipment_requirements": "Three projectors",
        "programme_notes": "Keynote at 10:30",
    }
    assert saved.previous_values == {
        "proposed_date": "2026-10-15",
        "end_date": "2026-10-15",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "expected_attendance": 250,
        "venue_requirements": "Main hall",
        "equipment_requirements": "Two projectors",
        "programme_notes": "Keynote at 09:30",
    }


def test_moving_the_date_moves_the_end_date_with_it(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    raise_change(ORGANISER_ID, {"proposed_date": "2026-10-20", "reason": REASON})

    [saved] = change_requests_of(saved_event_request.id)
    assert saved.requested_values == {"proposed_date": "2026-10-20", "end_date": "2026-10-20"}
    assert saved.previous_values == {"proposed_date": "2026-10-15", "end_date": "2026-10-15"}


def test_a_value_the_event_already_has_is_not_part_of_the_request(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    payload = {"start_time": "09:00", "expected_attendance": 300, "reason": REASON}

    raise_change(ORGANISER_ID, payload)

    [saved] = change_requests_of(saved_event_request.id)
    assert saved.requested_values == {"expected_attendance": 300}


def test_a_blank_requirement_asks_for_it_to_be_cleared(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
    save: Callable[..., None],
) -> None:
    saved_event_request.venue_requirements = "Main hall"
    save(saved_event_request)

    raise_change(ORGANISER_ID, {"venue_requirements": "   ", "reason": REASON})

    [saved] = change_requests_of(saved_event_request.id)
    assert saved.requested_values == {"venue_requirements": None}
    assert saved.previous_values == {"venue_requirements": "Main hall"}


@pytest.mark.parametrize(
    "field",
    [
        "name",
        "purpose",
        "description",
        "accessibility_needs",
        "internal_planning_notes",
        "registration_required",
        # Cancelling is the Organiser's own action, not a change request (SCRUM-61).
        "status",
    ],
)
def test_a_field_outside_the_list_is_refused(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
    field: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        raise_change(ORGANISER_ID, {**MORE_ATTENDEES, field: "cancelled"})

    assert exc_info.value.status_code == 400
    assert list(exc_info.value.details) == [field]
    _assert_nothing_raised(change_requests_of, saved_event_request.id)


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"expected_attendance": 0}, "expected_attendance"),
        ({"proposed_date": "2026-09-14"}, "proposed_date"),
        ({"end_time": "08:00"}, "end_time"),
        ({"start_time": "10:00+08:00"}, "start_time"),
    ],
    ids=["no-attendees", "date-in-the-past", "ends-before-it-starts", "time-with-offset"],
)
def test_a_requested_value_is_checked_as_an_edit_would_be(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
    payload: dict[str, Any],
    field: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        raise_change(ORGANISER_ID, {**payload, "reason": REASON})

    assert list(exc_info.value.details) == [field]
    _assert_nothing_raised(change_requests_of, saved_event_request.id)


def test_a_date_of_today_is_allowed(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    raise_change(ORGANISER_ID, {"proposed_date": "2026-09-15", "reason": REASON})

    [saved] = change_requests_of(saved_event_request.id)
    assert saved.requested_values["proposed_date"] == "2026-09-15"


# --------------------------------------------------------------------------
# AC3 — raising a change request leaves the event as it is
# --------------------------------------------------------------------------


def test_raising_a_change_request_leaves_the_event_unchanged(
    raise_change: RaiseChange,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    raise_change(ORGANISER_ID, {"proposed_date": "2026-10-20", **MORE_ATTENDEES})

    reloaded = reload_event_request(saved_event_request.id)
    assert (
        reloaded.status,
        reloaded.proposed_date.isoformat(),
        reloaded.end_date.isoformat(),
        reloaded.expected_attendance,
    ) == (EventRequestStatus.SUBMITTED, "2026-10-15", "2026-10-15", 250)


# --------------------------------------------------------------------------
# AC5 — the assigned coordinator is told
# --------------------------------------------------------------------------


def test_the_assigned_coordinator_is_told_what_should_change_and_why(
    raise_change: RaiseChange, detailed_notifications_of: DetailedNotificationsOf
) -> None:
    raise_change(ORGANISER_ID, {**MORE_ATTENDEES, "venue_requirements": "A bigger hall"})

    assert detailed_notifications_of(COORDINATOR_ID) == [
        (
            REFERENCE,
            NotificationKind.CHANGE_REQUEST_RAISED,
            f"Changes to expected attendance, venue requirements. Reason: {REASON}",
        )
    ]


def test_nobody_else_is_told(
    raise_change: RaiseChange,
    other_organisers: list[User],
    detailed_notifications_of: DetailedNotificationsOf,
) -> None:
    raise_change(ORGANISER_ID, MORE_ATTENDEES)

    for user_id in (OTHER_COORDINATOR_ID, ORGANISER_ID, COLLEAGUE_ID):
        assert detailed_notifications_of(user_id) == []


def test_with_no_coordinator_assigned_the_request_is_still_raised_and_logged(
    raise_change: RaiseChange,
    saved_event_request: EventRequest,
    save: Callable[..., None],
    change_requests_of: ChangeRequestsOf,
    detailed_notifications_of: DetailedNotificationsOf,
    caplog: pytest.LogCaptureFixture,
    db_session: Session,
) -> None:
    saved_event_request.coordinator_id = None
    save(saved_event_request)

    raise_change(ORGANISER_ID, MORE_ATTENDEES)
    # Only what was committed survives this, so the read below proves it was saved.
    db_session.rollback()

    assert len(change_requests_of(saved_event_request.id)) == 1
    assert detailed_notifications_of(COORDINATOR_ID) == []
    assert f"event_request_unassigned reference={REFERENCE}" in caplog.text


# --------------------------------------------------------------------------
# AC6 — refusals, each saying which
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", REFUSED_STATUSES, ids=lambda status: status.value)
def test_raising_is_refused_outside_submitted_to_confirmed(
    raise_change: RaiseChange,
    set_status: SetStatus,
    change_requests_of: ChangeRequestsOf,
    detailed_notifications_of: DetailedNotificationsOf,
    saved_event_request: EventRequest,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    with pytest.raises(ChangeRequestNotAllowedError) as exc_info:
        raise_change(ORGANISER_ID, MORE_ATTENDEES)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "change_request_not_allowed")
    assert refused.message == f"A change can't be requested for a {status.value} event."
    _assert_nothing_raised(change_requests_of, saved_event_request.id)
    assert detailed_notifications_of(COORDINATOR_ID) == []


@pytest.mark.parametrize(
    "reason",
    [pytest.param("", id="empty"), pytest.param("   ", id="spaces"), pytest.param(None, id="null")],
)
def test_raising_is_refused_without_a_reason(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
    reason: str | None,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        raise_change(ORGANISER_ID, {"expected_attendance": 300, "reason": reason})

    assert exc_info.value.details == {"reason": [CHANGE_REASON_REQUIRED_MESSAGE]}
    _assert_nothing_raised(change_requests_of, saved_event_request.id)


def test_raising_is_refused_when_the_reason_is_left_out(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        raise_change(ORGANISER_ID, {"expected_attendance": 300})

    assert exc_info.value.details == {"reason": [CHANGE_REASON_REQUIRED_MESSAGE]}
    _assert_nothing_raised(change_requests_of, saved_event_request.id)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"reason": REASON}, id="no-field"),
        pytest.param({"expected_attendance": 250, "reason": REASON}, id="only-current-values"),
    ],
)
def test_raising_is_refused_when_nothing_should_change(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        raise_change(ORGANISER_ID, payload)

    assert (exc_info.value.status_code, exc_info.value.message) == (400, NOTHING_TO_CHANGE_MESSAGE)
    _assert_nothing_raised(change_requests_of, saved_event_request.id)


def test_a_colleague_in_the_same_organisation_is_refused(
    raise_change: RaiseChange,
    other_organisers: list[User],
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    with pytest.raises(NotEventOrganiserError) as exc_info:
        raise_change(COLLEAGUE_ID, MORE_ATTENDEES)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code, refused.message) == (
        403,
        "not_event_organiser",
        NOT_THE_EVENTS_ORGANISER_MESSAGE,
    )
    _assert_nothing_raised(change_requests_of, saved_event_request.id)


def test_an_organiser_of_another_organisation_finds_no_such_event(
    raise_change: RaiseChange,
    other_organisers: list[User],
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        raise_change(OTHER_ORGANISATIONS_ORGANISER_ID, MORE_ATTENDEES)

    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    _assert_nothing_raised(change_requests_of, saved_event_request.id)


def test_an_organiser_with_no_organisation_is_refused(
    raise_change: RaiseChange, other_organisers: list[User]
) -> None:
    with pytest.raises(OrganiserWithoutOrganisationError):
        raise_change(UNLINKED_ORGANISER_ID, MORE_ATTENDEES)


def test_the_status_is_checked_before_the_payload(
    raise_change: RaiseChange, set_status: SetStatus
) -> None:
    set_status(EventRequestStatus.CANCELLED)

    with pytest.raises(ChangeRequestNotAllowedError):
        raise_change(ORGANISER_ID, {})


# --------------------------------------------------------------------------
# AC7 — one Pending change request per event
# --------------------------------------------------------------------------


def test_a_second_request_is_refused_while_the_first_is_pending(
    raise_change: RaiseChange,
    change_requests_of: ChangeRequestsOf,
    detailed_notifications_of: DetailedNotificationsOf,
    saved_event_request: EventRequest,
) -> None:
    raise_change(ORGANISER_ID, MORE_ATTENDEES)

    with pytest.raises(ConflictError) as exc_info:
        raise_change(ORGANISER_ID, {"start_time": "10:00", "reason": REASON})

    refused = exc_info.value
    assert (refused.status_code, refused.message) == (409, CHANGE_REQUEST_ALREADY_PENDING_MESSAGE)
    assert "already waiting for the coordinator" in refused.message
    assert len(change_requests_of(saved_event_request.id)) == 1
    assert len(detailed_notifications_of(COORDINATOR_ID)) == 1


@pytest.mark.parametrize(
    "status",
    [ChangeRequestStatus.WITHDRAWN, ChangeRequestStatus.APPROVED, ChangeRequestStatus.REJECTED],
    ids=lambda status: status.value,
)
def test_a_new_request_can_be_raised_once_the_last_is_no_longer_pending(
    raise_change: RaiseChange,
    save_change_request: SaveChangeRequest,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
    status: ChangeRequestStatus,
) -> None:
    save_change_request(saved_event_request, status)

    raise_change(ORGANISER_ID, MORE_ATTENDEES)

    statuses = [saved.status for saved in change_requests_of(saved_event_request.id)]
    assert statuses == [status, ChangeRequestStatus.PENDING]


def test_another_events_pending_request_does_not_block_this_one(
    raise_change: RaiseChange,
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
    save_change_request: SaveChangeRequest,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    other_event = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=COORDINATOR_ID)
    save(other_event)
    save_change_request(other_event)

    raise_change(ORGANISER_ID, MORE_ATTENDEES)

    assert len(change_requests_of(saved_event_request.id)) == 1


def test_the_database_refuses_a_second_pending_request_for_one_event(
    saved_users: list[User],
    saved_event_request: EventRequest,
    save_change_request: SaveChangeRequest,
    db_session: Session,
) -> None:
    save_change_request(saved_event_request)

    with pytest.raises(IntegrityError):
        save_change_request(saved_event_request)
    db_session.rollback()


def test_the_database_keeps_any_number_of_requests_no_longer_pending(
    saved_users: list[User],
    saved_event_request: EventRequest,
    save_change_request: SaveChangeRequest,
    change_requests_of: ChangeRequestsOf,
) -> None:
    for status in (ChangeRequestStatus.WITHDRAWN, ChangeRequestStatus.WITHDRAWN):
        save_change_request(saved_event_request, status)
    save_change_request(saved_event_request)

    assert len(change_requests_of(saved_event_request.id)) == 3


def test_an_integrity_error_other_than_a_second_pending_request_is_not_relabelled(
    mock_session: MagicMock,
    organiser_is_found: None,
    make_event_request: Callable[..., EventRequest],
) -> None:
    event_request = make_event_request(coordinator_id=COORDINATOR_ID)
    event_request.id = 1
    mock_session.scalar.return_value = event_request
    mock_session.scalars.return_value.one.return_value = event_request
    other_failure = IntegrityError(
        "INSERT INTO event_change_requests ...",
        {},
        Exception("FOREIGN KEY constraint failed"),
    )
    mock_session.commit.side_effect = other_failure

    with pytest.raises(IntegrityError) as exc_info:
        raise_change_request(ORGANISER_ID, REFERENCE, MORE_ATTENDEES, session=mock_session)

    assert exc_info.value is other_failure
    mock_session.rollback.assert_called_once()


# --------------------------------------------------------------------------
# ADR-0126 — raising locks the event's row
# --------------------------------------------------------------------------


def test_an_event_cancelled_while_waiting_for_the_lock_is_refused(
    raise_change: RaiseChange,
    on_event_row_lock: OnEventRowLock,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    """The session's copy predates the cancellation, so a stale read fails too."""
    assert saved_event_request.status is EventRequestStatus.SUBMITTED
    cancelled = (
        update(EventRequest)
        .where(EventRequest.id == saved_event_request.id)
        .values(status=EventRequestStatus.CANCELLED)
    )
    on_event_row_lock(lambda connection: connection.execute(cancelled))

    with pytest.raises(ChangeRequestNotAllowedError):
        raise_change(ORGANISER_ID, MORE_ATTENDEES)

    _assert_nothing_raised(change_requests_of, saved_event_request.id)
