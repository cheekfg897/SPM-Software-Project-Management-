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
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventHistoryKind, EventRequest
from app.modules.events.services import (
    DecisionAsShown,
    EventRecord,
    get_event_record_for_coordinator,
    get_event_record_for_organiser,
    record_event_history,
)

pytestmark = pytest.mark.scrum_31

OpenRecord = Callable[[], EventRecord]
RecordDecision = Callable[..., None]
OpenRecordRoute = Callable[[EventRecord], dict[str, Any]]
CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
ORGANISER_ID = 7
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
REASON = "The venue is too small for the expected attendance."
FIRST_DECIDED_AT = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)
LATEST_DECIDED_AT = datetime(2026, 9, 15, 2, 30, tzinfo=timezone.utc)


@pytest.fixture(
    params=[
        (get_event_record_for_organiser, ORGANISER_ID),
        (get_event_record_for_coordinator, COORDINATOR_ID),
    ],
    ids=["organiser", "coordinator"],
)
def open_record(request: pytest.FixtureRequest, saved_users: list[User]) -> OpenRecord:
    """Open ``REFERENCE``'s record as its organiser, or as its assigned coordinator."""
    get_record, viewer_id = request.param

    def _open() -> EventRecord:
        return get_record(viewer_id, REFERENCE)

    return _open


@pytest.fixture()
def record_decision(saved_event_request: EventRequest, db_session: Session) -> RecordDecision:
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
        record_event_history(
            saved_event_request,
            kind,
            actor_id=actor_id,
            details=details,
            session=db_session,
            now=occurred_at,
        )
        db_session.commit()

    return _record


@pytest.fixture()
def open_record_route(
    call_route: CallRoute,
    replace_services: ReplaceServices,
    token_for: Callable[..., str],
    make_user: Callable[..., User],
) -> OpenRecordRoute:
    """Call the record route as organiser 7, whose record is the one given."""
    token = token_for(make_user(role=Role.EVENT_ORGANISER, user_id=ORGANISER_ID))

    def _open(record: EventRecord) -> dict[str, Any]:
        replace_services(routes, {"get_event_record_for_organiser": record})
        response, status = call_route(
            "events.get_my_request",
            "GET",
            f"/api/events/requests/{REFERENCE}",
            {"reference": REFERENCE},
            token,
        )
        assert status == 200
        return response.get_json()

    return _open


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
    record = EventRecord(event_request=make_event_request(), coordinator=None, decision=decision)

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
    record = EventRecord(event_request=make_event_request(), coordinator=None)

    body = open_record_route(record)

    assert body["decision"] is None
