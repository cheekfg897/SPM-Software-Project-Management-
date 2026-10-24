"""Unit tests for SCRUM-31 "Review and decide a submitted request": the decision shown.

AC9: the organiser sees the current decision, its reason and the coordinator who made
it. AC8: every decision stays in the history and the latest one is current. The
decision is read from the latest ``decision_recorded`` history entry, with the
coordinator's name looked up when the record is read (ADR-0028). The coordinator's
view of the record shows the same section (SCRUM-24 AC9, ADR-0026).

The service tests run against ``db_session`` with ``saved_users``; the history entries
are written directly with ``record_event_history`` so their times can be pinned out of
insertion order.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest

from app.modules.events.models import EventHistoryKind, EventRequest
from app.modules.events.services import DecisionAsShown, EventRecord, OrganiserEventRecord

pytestmark = pytest.mark.scrum_31

OpenRecord = Callable[[], EventRecord]
RecordDecision = Callable[..., None]
RecordEntry = Callable[..., None]
OpenRecordRoute = Callable[[OrganiserEventRecord], dict[str, Any]]

#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
REASON = "The venue is too small for the expected attendance."
FIRST_DECIDED_AT = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)
LATEST_DECIDED_AT = datetime(2026, 9, 15, 2, 30, tzinfo=timezone.utc)


@pytest.fixture()
def record_decision(record_entry: RecordEntry) -> RecordDecision:
    """Save a history entry on ``saved_event_request`` at a pinned time.

    A ``decision_recorded`` entry by its coordinator unless told otherwise.
    """

    def _record(
        occurred_at: datetime,
        *,
        actor_id: int = COORDINATOR_ID,
        details: dict[str, Any] | None = None,
        kind: EventHistoryKind = EventHistoryKind.DECISION_RECORDED,
    ) -> None:
        record_entry(kind, occurred_at, actor_id=actor_id, details=details)

    return _record


# --------------------------------------------------------------------------
# AC8, AC9 — the record shows the latest decision, its reason and its coordinator
# --------------------------------------------------------------------------


def test_the_record_shows_the_latest_decision_with_its_reason_and_coordinator(
    open_record: OpenRecord, record_decision: RecordDecision
) -> None:
    # Written latest first, so only the time can make it the current one.
    record_decision(LATEST_DECIDED_AT, details={"outcome": "rejected", "reason": REASON})
    record_decision(FIRST_DECIDED_AT, details={"outcome": "approved", "reason": None})
    record_decision(
        datetime(2026, 9, 15, 3, 0, tzinfo=timezone.utc),
        details={"field": "name", "previous_value": "A", "new_value": "B", "significant": False},
        kind=EventHistoryKind.FIELD_CHANGED,
    )

    record = open_record()

    assert record.decision == DecisionAsShown(
        outcome="rejected",
        reason=REASON,
        decided_by="Coordinator Three",
        decided_at=LATEST_DECIDED_AT,
    )


def test_of_two_decisions_at_the_same_instant_the_one_recorded_last_is_current(
    open_record: OpenRecord, record_decision: RecordDecision
) -> None:
    record_decision(LATEST_DECIDED_AT, details={"outcome": "approved", "reason": None})
    record_decision(LATEST_DECIDED_AT, details={"outcome": "rejected", "reason": REASON})

    record = open_record()

    assert record.decision is not None
    assert (record.decision.outcome, record.decision.reason) == ("rejected", REASON)


def test_a_request_with_no_decision_shows_none(
    open_record: OpenRecord, record_decision: RecordDecision
) -> None:
    record_decision(FIRST_DECIDED_AT, kind=EventHistoryKind.REVIEW_STARTED)

    record = open_record()

    assert record.decision is None


def test_a_removed_coordinators_name_is_null(
    open_record: OpenRecord, record_decision: RecordDecision
) -> None:
    record_decision(LATEST_DECIDED_AT, actor_id=99, details={"outcome": "approved", "reason": None})

    record = open_record()

    assert record.decision == DecisionAsShown(
        outcome="approved", reason=None, decided_by=None, decided_at=LATEST_DECIDED_AT
    )


def test_a_decision_entry_with_no_details_is_shown_without_outcome_or_reason(
    open_record: OpenRecord, record_decision: RecordDecision
) -> None:
    record_decision(LATEST_DECIDED_AT, details=None)

    record = open_record()

    assert record.decision == DecisionAsShown(
        outcome=None, reason=None, decided_by="Coordinator Three", decided_at=LATEST_DECIDED_AT
    )


# --------------------------------------------------------------------------
# AC9 — the record route shows it as ``decision``
# --------------------------------------------------------------------------


def test_the_record_route_shows_the_decision_in_business_time(
    open_record_route: OpenRecordRoute, make_event_request: Callable[..., EventRequest]
) -> None:
    decision = DecisionAsShown(
        outcome="rejected",
        reason=REASON,
        decided_by="Coordinator Three",
        decided_at=LATEST_DECIDED_AT,
    )
    record = OrganiserEventRecord(
        event_request=make_event_request(), coordinator=None, decision=decision
    )

    body = open_record_route(record)

    assert body["decision"] == {
        "outcome": "rejected",
        "reason": REASON,
        "decided_by": "Coordinator Three",
        "decided_at": "2026-09-15T10:30:00+08:00",
    }


def test_the_record_route_shows_null_until_a_decision_is_recorded(
    open_record_route: OpenRecordRoute, make_event_request: Callable[..., EventRequest]
) -> None:
    record = OrganiserEventRecord(event_request=make_event_request(), coordinator=None)

    body = open_record_route(record)

    assert body["decision"] is None
