"""Unit tests for SCRUM-57 "Review and decide a change request": deciding it.

AC2: approving applies the requested values and records each change in the event
history, in every status a change request can be raised in, a Confirmed event included.
AC3: rejecting needs a reason and leaves the event and every arrangement as it was.
AC4: the Organiser is told of the decision and any reason. AC5: a change request can't
be decided twice; deciding locks the event's row, so of two decisions the first wins.
AC6: the decided request shows as Approved or Rejected on the event record, with who
decided it, when and why. Only the event's assigned coordinator decides (ADR-0127).

Runs against ``db_session`` with ``saved_users``, ``other_organisers`` and
``saved_event_request`` (``EVR-AAAAAAAA``: organiser 7's, assigned to Event Coordinator
3, Submitted, on 15 Oct 2026 from 09:00 to 17:00 for 250 people).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timezone
from typing import Any

import pytest
from sqlalchemy import Connection, select, update
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.equipment.models import EquipmentReservation, EquipmentType
from app.modules.events import services as events_services
from app.modules.events.models import (
    ChangeRequestStatus,
    EventChangeRequest,
    EventEquipmentLine,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    CHANGE_REQUESTABLE_STATUSES,
    ChangeRequestAsShown,
    ChangeRequestNotAllowedError,
    ChangeRequestNotPendingError,
    EventRecord,
    RequestedChange,
)
from app.modules.notifications.services import NotificationKind
from app.modules.venue.models import BookingRequestStatus, VenueBookingRequest
from tests.events.cases import Arrange, lose_connection

pytestmark = pytest.mark.scrum_57

RaiseChange = Callable[[int, Any], ChangeRequestAsShown]
DecideChange = Callable[[int, int, Any], ChangeRequestAsShown]
SaveChangeRequest = Callable[..., EventChangeRequest]
ChangeRequestsOf = Callable[[int], list[EventChangeRequest]]
ReloadEventRequest = Callable[[int], EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
DetailedNotificationsOf = Callable[[int], list[tuple[Any, ...]]]
OnEventRowLock = Callable[[Callable[[Connection], None]], None]

REFERENCE = "EVR-AAAAAAAA"
ORGANISER_ID = 7
ORGANISER_NAME = "Alice Example"
#: From ``other_organisers``: a colleague in organisation 3.
COLLEAGUE_ID = 8
COORDINATOR_ID = 3
COORDINATOR_NAME = "Coordinator Three"
OTHER_COORDINATOR_ID = 9
REASON = "More partners are coming."
APPROVE = {"outcome": "approved"}
APPROVE_WITH_REASON = {"outcome": "approved", "reason": "The hall holds 300."}
REJECTION_REASON = "The hall can't hold more."
REJECT = {"outcome": "rejected", "reason": REJECTION_REASON}
#: Every status but those a change can be raised in, and a draft, which no staff lookup
#: ever finds (ADR-0024).
STATUSES_A_CHANGE_CANT_BE_APPLIED_IN = sorted(
    set(EventRequestStatus) - CHANGE_REQUESTABLE_STATUSES - {EventRequestStatus.DRAFT},
    key=lambda status: status.value,
)
DECIDED_OR_WITHDRAWN = [
    ChangeRequestStatus.APPROVED,
    ChangeRequestStatus.REJECTED,
    ChangeRequestStatus.WITHDRAWN,
]
DECISIONS = [pytest.param(APPROVE, id="approve"), pytest.param(REJECT, id="reject")]


@pytest.fixture()
def raised(raise_change: RaiseChange) -> ChangeRequestAsShown:
    """Organiser 7's Pending request to move the event and change its numbers."""
    return raise_change(
        ORGANISER_ID,
        {
            "proposed_date": "2026-10-20",
            "start_time": "10:00",
            "expected_attendance": 300,
            "programme_notes": "Keynote moved to the afternoon.",
            "reason": REASON,
        },
    )


@pytest.fixture()
def pending(
    saved_users: list[User],
    saved_event_request: EventRequest,
    save_change_request: SaveChangeRequest,
) -> EventChangeRequest:
    """A Pending change request on ``saved_event_request``, for 300 attendees."""
    return save_change_request(saved_event_request)


def _event_details(event_request: EventRequest) -> dict[str, Any]:
    """What a change request could change on the event, and its status."""
    return {
        "status": event_request.status,
        "proposed_date": event_request.proposed_date,
        "end_date": event_request.end_date,
        "start_time": event_request.start_time,
        "end_time": event_request.end_time,
        "expected_attendance": event_request.expected_attendance,
        "venue_requirements": event_request.venue_requirements,
        "equipment_requirements": event_request.equipment_requirements,
        "programme_notes": event_request.programme_notes,
    }


#: ``saved_event_request``'s details as ``make_event_request`` saves them.
SAVED_DETAILS = {
    "status": EventRequestStatus.SUBMITTED,
    "proposed_date": date(2026, 10, 15),
    "end_date": date(2026, 10, 15),
    "start_time": time(9, 0),
    "end_time": time(17, 0),
    "expected_attendance": 250,
    "venue_requirements": None,
    "equipment_requirements": None,
    "programme_notes": None,
}


def _assert_nothing_decided(
    change_requests_of: ChangeRequestsOf,
    reload_event_request: ReloadEventRequest,
    detailed_notifications_of: DetailedNotificationsOf,
    event_request: EventRequest,
) -> None:
    """The request is still Pending, the event as saved, and the Organiser not told."""
    [saved] = change_requests_of(event_request.id)
    assert (saved.status, saved.decided_at, saved.decided_by) == (
        ChangeRequestStatus.PENDING,
        None,
        None,
    )
    assert _event_details(reload_event_request(event_request.id)) == SAVED_DETAILS
    assert detailed_notifications_of(ORGANISER_ID) == []


# --------------------------------------------------------------------------
# AC2 — approving applies the new values and records them in the history
# --------------------------------------------------------------------------


def test_approving_applies_every_requested_value(
    decide_change: DecideChange,
    raised: ChangeRequestAsShown,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    decide_change(COORDINATOR_ID, raised.id, APPROVE)

    assert _event_details(reload_event_request(saved_event_request.id)) == {
        **SAVED_DETAILS,
        "proposed_date": date(2026, 10, 20),
        # A one-day event moved by its date ends on its new date (ADR-0025).
        "end_date": date(2026, 10, 20),
        "start_time": time(10, 0),
        "expected_attendance": 300,
        "programme_notes": "Keynote moved to the afternoon.",
    }


def test_approving_records_each_change_in_the_history_as_the_coordinator(
    decide_change: DecideChange,
    raised: ChangeRequestAsShown,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
) -> None:
    decide_change(COORDINATOR_ID, raised.id, APPROVE)

    changed = EventHistoryKind.FIELD_CHANGED
    # In the order an edit records its changes (ADR-0025).
    assert history_of(saved_event_request.id) == [
        (
            changed,
            COORDINATOR_ID,
            {
                "field": "programme_notes",
                "previous_value": None,
                "new_value": "Keynote moved to the afternoon.",
                "significant": False,
            },
        ),
        (
            changed,
            COORDINATOR_ID,
            {
                "field": "proposed_date",
                "previous_value": "2026-10-15",
                "new_value": "2026-10-20",
                "significant": True,
            },
        ),
        (
            changed,
            COORDINATOR_ID,
            {
                "field": "end_date",
                "previous_value": "2026-10-15",
                "new_value": "2026-10-20",
                "significant": True,
            },
        ),
        (
            changed,
            COORDINATOR_ID,
            {
                "field": "start_time",
                "previous_value": "09:00:00",
                "new_value": "10:00:00",
                "significant": True,
            },
        ),
        (
            changed,
            COORDINATOR_ID,
            {
                "field": "expected_attendance",
                "previous_value": 250,
                "new_value": 300,
                "significant": True,
            },
        ),
    ]


@pytest.mark.parametrize(
    "status", sorted(CHANGE_REQUESTABLE_STATUSES, key=lambda status: status.value)
)
def test_approving_applies_the_change_in_every_status_one_can_be_raised_in(
    decide_change: DecideChange,
    raise_change: RaiseChange,
    set_status: Callable[[EventRequestStatus], None],
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
    status: EventRequestStatus,
) -> None:
    """A Confirmed event can't be edited directly, but an approved change applies to it.

    The event stays in its status: what a change does to its arrangements, and so to
    its status, is SCRUM-58's.
    """
    set_status(status)
    raised = raise_change(ORGANISER_ID, {"expected_attendance": 300, "reason": REASON})

    decide_change(COORDINATOR_ID, raised.id, APPROVE)

    saved = reload_event_request(saved_event_request.id)
    assert (saved.status, saved.expected_attendance) == (status, 300)


def test_an_approved_equipment_requirements_change_edits_the_text_not_the_lines(
    decide_change: DecideChange,
    raise_change: RaiseChange,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
    reload_event_request: ReloadEventRequest,
    db_session: Session,
) -> None:
    """ADR-0128, a default pending the Product Owner: lines stay the coordinator's."""
    line = make_equipment_line(saved_event_request, equipment_type)
    save(line)
    raised = raise_change(
        ORGANISER_ID, {"equipment_requirements": "Four projectors", "reason": REASON}
    )

    decide_change(COORDINATOR_ID, raised.id, APPROVE)

    assert reload_event_request(saved_event_request.id).equipment_requirements == (
        "Four projectors"
    )
    [saved_line] = db_session.scalars(select(EventEquipmentLine))
    assert (saved_line.equipment_type_id, saved_line.quantity, saved_line.notes) == (
        equipment_type.id,
        2,
        "Needs HDMI",
    )


@pytest.mark.parametrize("status", STATUSES_A_CHANGE_CANT_BE_APPLIED_IN, ids=lambda s: s.value)
def test_a_change_is_not_applied_to_an_event_that_is_over(
    decide_change: DecideChange,
    pending: EventChangeRequest,
    set_status: Callable[[EventRequestStatus], None],
    change_requests_of: ChangeRequestsOf,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
    status: EventRequestStatus,
) -> None:
    """ADR-0127: a completed event ran as it was; the request can still be rejected."""
    set_status(status)

    with pytest.raises(ChangeRequestNotAllowedError) as exc_info:
        decide_change(COORDINATOR_ID, pending.id, APPROVE)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "change_request_not_allowed")
    assert refused.message == (
        f"A change can't be applied to a {status.value} event. Reject the change request instead."
    )
    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is ChangeRequestStatus.PENDING
    assert reload_event_request(saved_event_request.id).expected_attendance == 250


@pytest.mark.parametrize("status", STATUSES_A_CHANGE_CANT_BE_APPLIED_IN, ids=lambda s: s.value)
def test_a_change_request_on_an_event_that_is_over_can_still_be_rejected(
    decide_change: DecideChange,
    pending: EventChangeRequest,
    set_status: Callable[[EventRequestStatus], None],
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    decide_change(COORDINATOR_ID, pending.id, REJECT)

    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is ChangeRequestStatus.REJECTED


# --------------------------------------------------------------------------
# AC3 — rejecting needs a reason and leaves everything as it was
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason",
    [{}, {"reason": None}, {"reason": ""}, {"reason": "   "}],
    ids=["missing", "null", "empty", "blank"],
)
def test_rejecting_without_a_reason_is_refused(
    decide_change: DecideChange,
    pending: EventChangeRequest,
    change_requests_of: ChangeRequestsOf,
    reload_event_request: ReloadEventRequest,
    detailed_notifications_of: DetailedNotificationsOf,
    saved_event_request: EventRequest,
    reason: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        decide_change(COORDINATOR_ID, pending.id, {"outcome": "rejected", **reason})

    assert exc_info.value.status_code == 400
    assert "reason" in exc_info.value.details
    _assert_nothing_decided(
        change_requests_of, reload_event_request, detailed_notifications_of, saved_event_request
    )


def test_a_rejection_with_no_reason_says_a_reason_is_needed(
    decide_change: DecideChange, pending: EventChangeRequest
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        decide_change(COORDINATOR_ID, pending.id, {"outcome": "rejected"})

    assert exc_info.value.details == {"reason": ["Say why the change request is rejected."]}


def test_an_outcome_other_than_approved_or_rejected_is_refused(
    decide_change: DecideChange, pending: EventChangeRequest
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        decide_change(COORDINATOR_ID, pending.id, {"outcome": "withdrawn", "reason": "No."})

    assert exc_info.value.details == {"outcome": ["Outcome must be approved or rejected."]}


@pytest.mark.parametrize(
    ("decision", "status", "start_time", "history_entries"),
    [
        pytest.param(APPROVE, ChangeRequestStatus.APPROVED, time(10, 0), 5, id="approve"),
        pytest.param(
            APPROVE_WITH_REASON,
            ChangeRequestStatus.APPROVED,
            time(10, 0),
            5,
            id="approve-with-a-reason",
        ),
        pytest.param(REJECT, ChangeRequestStatus.REJECTED, time(9, 0), 0, id="reject"),
    ],
)
def test_the_decision_is_committed_even_when_every_notice_fails(
    decide_change: DecideChange,
    raised: ChangeRequestAsShown,
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    change_requests_of: ChangeRequestsOf,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
    decision: dict[str, Any],
    status: ChangeRequestStatus,
    start_time: time,
    history_entries: int,
) -> None:
    """ADR-0015: the Organiser's notice commits too, and would hide a missing commit."""
    monkeypatch.setattr(events_services, "notify_users", lose_connection)

    decide_change(COORDINATOR_ID, raised.id, decision)
    # Only what was committed survives this, so the reads below prove it was saved.
    db_session.rollback()

    [saved] = change_requests_of(saved_event_request.id)
    assert (saved.status, saved.decided_by) == (status, COORDINATOR_ID)
    assert saved.decision_reason == decision.get("reason")
    assert saved.decided_at is not None
    assert reload_event_request(saved_event_request.id).start_time == start_time
    assert len(history_of(saved_event_request.id)) == history_entries


def test_rejecting_saves_the_rejection_and_its_reason(
    decide_change: DecideChange,
    pending: EventChangeRequest,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    before = datetime.now(timezone.utc)

    decide_change(COORDINATOR_ID, pending.id, {"outcome": "rejected", "reason": "  Too big. "})

    after = datetime.now(timezone.utc)
    [saved] = change_requests_of(saved_event_request.id)
    assert (saved.status, saved.decided_by, saved.decision_reason) == (
        ChangeRequestStatus.REJECTED,
        COORDINATOR_ID,
        "Too big.",
    )
    assert saved.decided_at is not None
    assert before <= saved.decided_at <= after


def test_rejecting_leaves_the_event_and_every_arrangement_untouched(
    decide_change: DecideChange,
    raised: ChangeRequestAsShown,
    arrange: Arrange,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    reserve: Callable[[EventRequest], EquipmentReservation],
    save: Callable[..., None],
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
    db_session: Session,
) -> None:
    arrange(BookingRequestStatus.APPROVED)
    arrange(BookingRequestStatus.PENDING)
    save(make_equipment_line(saved_event_request, equipment_type))
    reserve(saved_event_request)

    decide_change(COORDINATOR_ID, raised.id, REJECT)

    db_session.expire_all()
    assert _event_details(reload_event_request(saved_event_request.id)) == SAVED_DETAILS
    arrangements = db_session.scalars(select(VenueBookingRequest).order_by(VenueBookingRequest.id))
    assert [arrangement.status for arrangement in arrangements] == [
        BookingRequestStatus.APPROVED,
        BookingRequestStatus.PENDING,
    ]
    [line] = db_session.scalars(select(EventEquipmentLine))
    assert (line.quantity, line.notes) == (2, "Needs HDMI")
    [reservation] = db_session.scalars(select(EquipmentReservation))
    assert reservation.quantity == 4
    assert history_of(saved_event_request.id) == []


# --------------------------------------------------------------------------
# AC4 — the Organiser is told of the decision and any reason
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "kind", "detail"),
    [
        pytest.param(APPROVE, NotificationKind.CHANGE_REQUEST_APPROVED, None, id="approved"),
        pytest.param(
            {"outcome": "approved", "reason": "Fine by the venue."},
            NotificationKind.CHANGE_REQUEST_APPROVED,
            "Fine by the venue.",
            id="approved-with-a-reason",
        ),
        pytest.param(
            REJECT, NotificationKind.CHANGE_REQUEST_REJECTED, REJECTION_REASON, id="rejected"
        ),
    ],
)
def test_the_organiser_is_told_of_the_decision_and_any_reason_and_nobody_else(
    decide_change: DecideChange,
    pending: EventChangeRequest,
    other_organisers: list[User],
    detailed_notifications_of: DetailedNotificationsOf,
    payload: dict[str, Any],
    kind: NotificationKind,
    detail: str | None,
) -> None:
    decide_change(COORDINATOR_ID, pending.id, payload)

    assert detailed_notifications_of(ORGANISER_ID) == [(REFERENCE, kind, detail)]
    for user_id in (COLLEAGUE_ID, COORDINATOR_ID, OTHER_COORDINATOR_ID):
        assert detailed_notifications_of(user_id) == []


# --------------------------------------------------------------------------
# AC5 — a change request can't be decided twice
# --------------------------------------------------------------------------


@pytest.mark.parametrize("payload", DECISIONS)
@pytest.mark.parametrize("status", DECIDED_OR_WITHDRAWN, ids=lambda status: status.value)
def test_a_request_no_longer_pending_cannot_be_decided(
    decide_change: DecideChange,
    saved_users: list[User],
    saved_event_request: EventRequest,
    save_change_request: SaveChangeRequest,
    change_requests_of: ChangeRequestsOf,
    reload_event_request: ReloadEventRequest,
    detailed_notifications_of: DetailedNotificationsOf,
    status: ChangeRequestStatus,
    payload: dict[str, Any],
) -> None:
    closed = save_change_request(saved_event_request, status)

    with pytest.raises(ChangeRequestNotPendingError) as exc_info:
        decide_change(COORDINATOR_ID, closed.id, payload)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "change_request_not_pending")
    assert refused.message == (
        f"Only a pending change request can be decided; this one is {status.value}."
    )
    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is status
    assert reload_event_request(saved_event_request.id).expected_attendance == 250
    assert detailed_notifications_of(ORGANISER_ID) == []


def test_the_second_of_two_decisions_is_refused_and_the_first_stands(
    decide_change: DecideChange,
    raised: ChangeRequestAsShown,
    change_requests_of: ChangeRequestsOf,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    decide_change(COORDINATOR_ID, raised.id, APPROVE)

    with pytest.raises(ChangeRequestNotPendingError):
        decide_change(COORDINATOR_ID, raised.id, REJECT)

    [saved] = change_requests_of(saved_event_request.id)
    assert (saved.status, saved.decision_reason) == (ChangeRequestStatus.APPROVED, None)
    assert reload_event_request(saved_event_request.id).expected_attendance == 300


@pytest.mark.parametrize(
    "closed_values",
    [
        pytest.param(
            {
                "status": ChangeRequestStatus.REJECTED,
                "decided_at": datetime(2026, 9, 16, tzinfo=timezone.utc),
                "decided_by": COORDINATOR_ID,
                "decision_reason": REJECTION_REASON,
            },
            id="rejected",
        ),
        pytest.param(
            {
                "status": ChangeRequestStatus.WITHDRAWN,
                "withdrawn_at": datetime(2026, 9, 16, tzinfo=timezone.utc),
            },
            id="withdrawn",
        ),
    ],
)
def test_a_request_closed_while_waiting_for_the_lock_is_not_approved(
    decide_change: DecideChange,
    pending: EventChangeRequest,
    on_event_row_lock: OnEventRowLock,
    change_requests_of: ChangeRequestsOf,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
    db_session: Session,
    closed_values: dict[str, Any],
) -> None:
    """Technical note: what committed first stands, so the event is left as it is.

    Nothing of the request is held in the session beforehand, as in a real request, so
    only the lock decides whether the earlier decision or withdrawal is seen.
    """
    change_request_id = pending.id
    db_session.expire_all()
    closed = (
        update(EventChangeRequest)
        .where(EventChangeRequest.id == change_request_id)
        .values(**closed_values)
    )
    on_event_row_lock(lambda connection: connection.execute(closed))

    with pytest.raises(ChangeRequestNotPendingError):
        decide_change(COORDINATOR_ID, change_request_id, APPROVE)

    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is closed_values["status"]
    assert reload_event_request(saved_event_request.id).expected_attendance == 250


# --------------------------------------------------------------------------
# AC6 — the decided request shows as Approved or Rejected on the record
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "status", "reason"),
    [
        pytest.param(APPROVE, ChangeRequestStatus.APPROVED, None, id="approved"),
        pytest.param(REJECT, ChangeRequestStatus.REJECTED, REJECTION_REASON, id="rejected"),
    ],
)
def test_the_decided_request_shows_on_the_record_with_who_decided_it_and_why(
    decide_change: DecideChange,
    pending: EventChangeRequest,
    open_record: Callable[[], EventRecord],
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
    payload: dict[str, Any],
    status: ChangeRequestStatus,
    reason: str | None,
) -> None:
    decided = decide_change(COORDINATOR_ID, pending.id, payload)

    [saved] = change_requests_of(saved_event_request.id)
    expected = ChangeRequestAsShown(
        id=pending.id,
        status=status,
        changes=(RequestedChange("expected_attendance", 250, 300),),
        reason=REASON,
        raised_by=ORGANISER_NAME,
        raised_at=datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc),
        withdrawn_at=None,
        withdrawal_note=None,
        decided_by=COORDINATOR_NAME,
        decided_at=saved.decided_at,
        decision_reason=reason,
    )
    assert decided == expected
    assert open_record().change_requests == (expected,)


# --------------------------------------------------------------------------
# ADR-0127 — only the event's assigned coordinator decides, and only its requests
# --------------------------------------------------------------------------


@pytest.mark.parametrize("payload", DECISIONS)
def test_another_coordinator_gets_not_found_and_nothing_is_decided(
    decide_change: DecideChange,
    pending: EventChangeRequest,
    change_requests_of: ChangeRequestsOf,
    reload_event_request: ReloadEventRequest,
    detailed_notifications_of: DetailedNotificationsOf,
    saved_event_request: EventRequest,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        decide_change(OTHER_COORDINATOR_ID, pending.id, payload)

    assert exc_info.value.message == "Event request not found."
    _assert_nothing_decided(
        change_requests_of, reload_event_request, detailed_notifications_of, saved_event_request
    )


def test_an_event_with_no_coordinator_is_not_found(
    decide_change: DecideChange,
    pending: EventChangeRequest,
    saved_event_request: EventRequest,
    save: Callable[..., None],
) -> None:
    saved_event_request.coordinator_id = None
    save(saved_event_request)

    with pytest.raises(NotFoundError):
        decide_change(COORDINATOR_ID, pending.id, APPROVE)


def test_a_change_request_of_another_event_is_not_found_and_left_pending(
    decide_change: DecideChange,
    saved_users: list[User],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
    save_change_request: SaveChangeRequest,
    change_requests_of: ChangeRequestsOf,
) -> None:
    other_event = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=COORDINATOR_ID)
    save(other_event)
    others = save_change_request(other_event)

    with pytest.raises(NotFoundError) as exc_info:
        decide_change(COORDINATOR_ID, others.id, APPROVE)

    assert exc_info.value.message == "Change request not found."
    [saved] = change_requests_of(other_event.id)
    assert saved.status is ChangeRequestStatus.PENDING
