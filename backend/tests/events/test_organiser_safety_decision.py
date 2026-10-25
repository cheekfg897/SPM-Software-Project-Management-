"""Unit tests for SCRUM-49 AC11 — the Safety Officer's final decision, for organisers.

The Product Owner (25 Oct) asked for the Safety Officer's final decision on the
confirmed event to be shown to its organiser (ADR-0099). Once the event is Confirmed,
and still once it is Completed, the organiser's record shows the outcome of the current
safety check and when it was made. Before then it shows none. The officer's name, the
checklist notes and the reason stay internal. That the coordinator's record has no
such section is checked with its venue list in ``test_organiser_confirmed_venues.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from app.modules.auth.models import User
from app.modules.events.models import (
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
    SafetyOutcome,
)
from app.modules.events.services import (
    OrganiserEventRecord,
    OrganiserSafetyDecision,
    get_event_record_for_organiser,
)

pytestmark = pytest.mark.scrum_49

ORGANISER_ID = 7
COORDINATOR_ID = 3
SAFETY_OFFICER_ID = 4
REFERENCE = "EVR-AAAAAAAA"
#: The statuses in which the organiser sees the decision: once the event is confirmed.
DECISION_SHOWN_STATUSES = [EventRequestStatus.CONFIRMED, EventRequestStatus.COMPLETED]
#: Every other status, built from the enum so a new status is checked too.
DECISION_HIDDEN_STATUSES = [
    status for status in EventRequestStatus if status not in DECISION_SHOWN_STATUSES
]
SENT_AT = datetime(2026, 10, 20, 1, 0, tzinfo=UTC)
CHANGES_REQUESTED_AT = datetime(2026, 10, 21, 2, 0, tzinfo=UTC)
SENT_AGAIN_AT = datetime(2026, 10, 22, 3, 0, tzinfo=UTC)
APPROVED_AT = datetime(2026, 10, 23, 4, 30, tzinfo=UTC)
CHECKLIST = {"emergency_access": "Two exits, both signed."}
APPROVED_ON_23_OCT = OrganiserSafetyDecision(outcome=SafetyOutcome.APPROVED, decided_at=APPROVED_AT)

RecordEntry = Callable[..., None]


def _outcome(entry: RecordEntry, outcome: SafetyOutcome, at: datetime) -> None:
    """Save the Safety Officer's outcome, with checklist notes and a reason."""
    details = {"outcome": outcome.value, "checklist": CHECKLIST, "reason": "Keep aisles clear."}
    entry(
        EventHistoryKind.SAFETY_OUTCOME_RECORDED,
        at,
        actor_id=SAFETY_OFFICER_ID,
        details=details,
    )


def _sent_to_safety_review(entry: RecordEntry, at: datetime) -> None:
    entry(EventHistoryKind.SAFETY_REVIEW_REQUESTED, at, actor_id=COORDINATOR_ID, details=None)


@pytest.fixture()
def approved_after_changes(record_entry: RecordEntry) -> None:
    """Sent, sent back with changes requested, sent again, then approved on 23 Oct."""
    _sent_to_safety_review(record_entry, SENT_AT)
    _outcome(record_entry, SafetyOutcome.CHANGES_REQUESTED, CHANGES_REQUESTED_AT)
    _sent_to_safety_review(record_entry, SENT_AGAIN_AT)
    _outcome(record_entry, SafetyOutcome.APPROVED, APPROVED_AT)


# --------------------------------------------------------------------------
# The organiser's record, by the event's status
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", DECISION_SHOWN_STATUSES, ids=lambda status: status.value)
def test_once_confirmed_the_organisers_record_shows_the_final_decision_and_when(
    saved_users: list[User],
    set_status: Callable[[EventRequestStatus], None],
    approved_after_changes: None,
    status: EventRequestStatus,
) -> None:
    """The earlier "changes requested" is not the final decision, so it isn't shown."""
    set_status(status)

    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE)

    assert record.safety_decision == APPROVED_ON_23_OCT


@pytest.mark.parametrize("status", DECISION_HIDDEN_STATUSES, ids=lambda status: status.value)
def test_before_it_is_confirmed_the_organisers_record_shows_no_decision(
    saved_users: list[User],
    set_status: Callable[[EventRequestStatus], None],
    approved_after_changes: None,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE)

    assert record.safety_decision is None


def test_a_confirmed_event_with_no_current_outcome_shows_no_decision(
    saved_users: list[User],
    set_status: Callable[[EventRequestStatus], None],
    record_entry: RecordEntry,
) -> None:
    """Sent to Safety Review and not yet ruled on: there is no decision to show."""
    _sent_to_safety_review(record_entry, SENT_AT)
    set_status(EventRequestStatus.CONFIRMED)

    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE)

    assert record.safety_decision is None


# --------------------------------------------------------------------------
# How the record route shows it
# --------------------------------------------------------------------------


def _organisers_record(
    make_event_request: Callable[..., EventRequest], decision: OrganiserSafetyDecision | None
) -> OrganiserEventRecord:
    event_request = make_event_request(status=EventRequestStatus.CONFIRMED)
    return OrganiserEventRecord(
        event_request=event_request, coordinator=None, safety_decision=decision
    )


def test_the_route_shows_only_the_outcome_and_when_in_business_time(
    open_record_route: Callable[[OrganiserEventRecord], dict[str, Any]],
    make_event_request: Callable[..., EventRequest],
) -> None:
    """No officer, checklist or reason: the dump has exactly these two fields."""
    body = open_record_route(_organisers_record(make_event_request, APPROVED_ON_23_OCT))

    assert body["safety_decision"] == {
        "outcome": "approved",
        "decided_at": "2026-10-23T12:30:00+08:00",
    }


def test_the_route_shows_null_until_there_is_a_decision_to_show(
    open_record_route: Callable[[OrganiserEventRecord], dict[str, Any]],
    make_event_request: Callable[..., EventRequest],
) -> None:
    body = open_record_route(_organisers_record(make_event_request, None))

    assert body["safety_decision"] is None
