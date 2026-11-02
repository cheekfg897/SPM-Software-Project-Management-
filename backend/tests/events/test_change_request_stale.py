"""Unit tests for SCRUM-57 AC8: a stale change request isn't approved.

Approving is refused if a field the change request changes no longer has the value it
had when the request was raised, for example attendance raised from 250 to 300 after
the coordinator edited it to 120. The message names each such field and its value then
and now, and the request stays Pending so the coordinator can reject it. The requested
values are also checked again as an edit checks them, against the event as it is now,
so an approval never saves an event that ends before it starts (ADR-0127).

Runs against ``db_session`` with ``saved_users`` and ``approved_event_request``
(``EVR-AAAAAAAA``, Approved, on 15 Oct 2026 from 09:00 to 17:00 for 250 people, with
Event Coordinator 3), so the coordinator may edit it directly (SCRUM-33, SCRUM-110).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.events.models import (
    ChangeRequestStatus,
    EventChangeRequest,
    EventHistoryKind,
    EventRequest,
)
from app.modules.events.services import (
    ChangeRequestAsShown,
    ChangeRequestStaleError,
    EventEdit,
    decide_change_request,
)

pytestmark = pytest.mark.scrum_57

RaiseChange = Callable[[int, Any], ChangeRequestAsShown]
DecideChange = Callable[[int, int, Any], ChangeRequestAsShown]
EditEvent = Callable[[int, dict[str, Any] | None], EventEdit]
ChangeRequestsOf = Callable[[int], list[EventChangeRequest]]
ReloadEventRequest = Callable[[int], EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
DetailedNotificationsOf = Callable[[int], list[tuple[Any, ...]]]

ORGANISER_ID = 7
COORDINATOR_ID = 3
REASON = "Plans have changed."
APPROVE = {"outcome": "approved"}
STALE_OPENING = (
    "This change request can't be approved because the event has changed since it was raised."
)
STALE_CLOSING = "Reject it, and the organiser can raise a new one."


@pytest.fixture(autouse=True)
def _approved(approved_event_request: EventRequest) -> None:
    """Approve the event, so its coordinator may edit it directly (SCRUM-110)."""


def _stale_message(*fields: str) -> str:
    return " ".join((STALE_OPENING, *fields, STALE_CLOSING))


@pytest.mark.parametrize(
    ("requested", "edited", "fields_then_and_now"),
    [
        pytest.param(
            {"proposed_date": "2026-10-20"},
            {"proposed_date": "2026-10-18"},
            # The end date moved with the start, so it has changed since as well.
            (
                "Proposed date: 2026-10-15 when the change was requested, 2026-10-18 now.",
                "End date: 2026-10-15 when the change was requested, 2026-10-18 now.",
            ),
            id="date",
        ),
        pytest.param(
            {"start_time": "10:00"},
            {"start_time": "08:30"},
            ("Start time: 09:00 when the change was requested, 08:30 now.",),
            id="time",
        ),
        pytest.param(
            {"expected_attendance": 300},
            {"expected_attendance": 120},
            ("Expected attendance: 250 when the change was requested, 120 now.",),
            id="number",
        ),
        pytest.param(
            {"venue_requirements": "A stage"},
            {"venue_requirements": "Two rooms"},
            ("Venue requirements: blank when the change was requested, Two rooms now.",),
            id="text",
        ),
    ],
)
def test_approving_is_refused_when_a_requested_field_has_since_changed(
    raise_change: RaiseChange,
    edit_event: EditEvent,
    decide_change: DecideChange,
    change_requests_of: ChangeRequestsOf,
    history_of: HistoryOf,
    detailed_notifications_of: DetailedNotificationsOf,
    saved_event_request: EventRequest,
    requested: dict[str, Any],
    edited: dict[str, Any],
    fields_then_and_now: tuple[str, ...],
) -> None:
    raised = raise_change(ORGANISER_ID, {**requested, "reason": REASON})
    edit_event(COORDINATOR_ID, edited)
    history_before = history_of(saved_event_request.id)

    with pytest.raises(ChangeRequestStaleError) as exc_info:
        decide_change(COORDINATOR_ID, raised.id, APPROVE)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "change_request_stale")
    assert refused.message == _stale_message(*fields_then_and_now)
    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is ChangeRequestStatus.PENDING
    # Nothing was applied: the history holds only the coordinator's edit.
    assert history_of(saved_event_request.id) == history_before
    assert detailed_notifications_of(ORGANISER_ID) == []


def test_every_field_that_has_changed_is_named_in_the_requests_order(
    raise_change: RaiseChange,
    edit_event: EditEvent,
    decide_change: DecideChange,
) -> None:
    raised = raise_change(
        ORGANISER_ID,
        {"end_time": "18:00", "expected_attendance": 300, "reason": REASON},
    )
    edit_event(COORDINATOR_ID, {"expected_attendance": 120, "end_time": "16:00"})

    with pytest.raises(ChangeRequestStaleError) as exc_info:
        decide_change(COORDINATOR_ID, raised.id, APPROVE)

    assert exc_info.value.message == _stale_message(
        "End time: 17:00 when the change was requested, 16:00 now.",
        "Expected attendance: 250 when the change was requested, 120 now.",
    )


def test_a_field_cleared_since_is_named_as_blank_now(
    raise_change: RaiseChange,
    edit_event: EditEvent,
    decide_change: DecideChange,
) -> None:
    edit_event(COORDINATOR_ID, {"programme_notes": "Keynote at ten."})
    raised = raise_change(ORGANISER_ID, {"programme_notes": "Keynote at two.", "reason": REASON})
    edit_event(COORDINATOR_ID, {"programme_notes": ""})

    with pytest.raises(ChangeRequestStaleError) as exc_info:
        decide_change(COORDINATOR_ID, raised.id, APPROVE)

    assert exc_info.value.message == _stale_message(
        "Programme notes: Keynote at ten. when the change was requested, blank now."
    )


def test_a_stale_request_can_still_be_rejected(
    raise_change: RaiseChange,
    edit_event: EditEvent,
    decide_change: DecideChange,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    raised = raise_change(ORGANISER_ID, {"expected_attendance": 300, "reason": REASON})
    edit_event(COORDINATOR_ID, {"expected_attendance": 120})

    decide_change(COORDINATOR_ID, raised.id, {"outcome": "rejected", "reason": "Out of date."})

    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is ChangeRequestStatus.REJECTED


def test_a_change_to_a_field_the_request_leaves_alone_does_not_make_it_stale(
    raise_change: RaiseChange,
    edit_event: EditEvent,
    decide_change: DecideChange,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    raised = raise_change(ORGANISER_ID, {"expected_attendance": 300, "reason": REASON})
    edit_event(COORDINATOR_ID, {"programme_notes": "Keynote at ten."})

    decide_change(COORDINATOR_ID, raised.id, APPROVE)

    saved = reload_event_request(saved_event_request.id)
    assert (saved.expected_attendance, saved.programme_notes) == (300, "Keynote at ten.")


def test_a_field_changed_and_changed_back_is_not_stale(
    raise_change: RaiseChange,
    edit_event: EditEvent,
    decide_change: DecideChange,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    raised = raise_change(ORGANISER_ID, {"expected_attendance": 300, "reason": REASON})
    edit_event(COORDINATOR_ID, {"expected_attendance": 120})
    edit_event(COORDINATOR_ID, {"expected_attendance": 250})

    decide_change(COORDINATOR_ID, raised.id, APPROVE)

    assert reload_event_request(saved_event_request.id).expected_attendance == 300


# --------------------------------------------------------------------------
# ADR-0127 — the requested values are checked again against the event as it is now
# --------------------------------------------------------------------------


def test_a_change_that_would_end_the_event_before_it_starts_is_refused(
    raise_change: RaiseChange,
    edit_event: EditEvent,
    decide_change: DecideChange,
    change_requests_of: ChangeRequestsOf,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    """The request moves the end to 12:00; the coordinator has since moved the start."""
    raised = raise_change(ORGANISER_ID, {"end_time": "12:00", "reason": REASON})
    edit_event(COORDINATOR_ID, {"start_time": "13:00"})

    with pytest.raises(ValidationError) as exc_info:
        decide_change(COORDINATOR_ID, raised.id, APPROVE)

    assert exc_info.value.status_code == 400
    assert "end_time" in exc_info.value.details
    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is ChangeRequestStatus.PENDING
    assert reload_event_request(saved_event_request.id).end_time.isoformat() == "17:00:00"


#: The event is moved to 1 Oct; the change is decided on or after that day.
MOVE_TO_1_OCTOBER = {"proposed_date": "2026-10-01", "reason": REASON}


def _approve_on(change_request_id: int, approved_on: date) -> ChangeRequestAsShown:
    return decide_change_request(
        COORDINATOR_ID, "EVR-AAAAAAAA", change_request_id, APPROVE, today=approved_on
    )


def test_a_new_date_is_applied_when_approved_on_that_day(
    raise_change: RaiseChange, saved_users: list[User]
) -> None:
    raised = raise_change(ORGANISER_ID, MOVE_TO_1_OCTOBER)

    decided = _approve_on(raised.id, date(2026, 10, 1))

    assert decided.status is ChangeRequestStatus.APPROVED


def test_a_new_date_that_has_passed_by_the_time_of_approval_is_refused(
    raise_change: RaiseChange,
    saved_users: list[User],
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    raised = raise_change(ORGANISER_ID, MOVE_TO_1_OCTOBER)

    with pytest.raises(ValidationError) as exc_info:
        _approve_on(raised.id, date(2026, 10, 2))

    assert "proposed_date" in exc_info.value.details
    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is ChangeRequestStatus.PENDING
