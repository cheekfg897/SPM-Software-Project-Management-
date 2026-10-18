"""Unit tests for SCRUM-31 "Review and decide a submitted request": changing a decision.

AC6: the assigned coordinator may decide an approved or rejected request again, with
a reason, and the status follows the new decision; the same outcome may be given
again (ADR-0028). AC7: no new decision once the event has an equipment request (and,
with SCRUM-42, a venue booking request); the first decision is never blocked. AC8:
every decision stays in the history and the latest is current. AC10: the organiser is
told of each new decision.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, by organiser 7, submitted, assigned to Event Coordinator 3).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.common.errors import ValidationError
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import (
    EventEquipmentLine,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    DECISION_LOCKED_MESSAGE,
    REASON_REQUIRED_MESSAGE,
    DecisionAsShown,
    DecisionLockedError,
    decide_event_request,
    get_event_record_for_organiser,
)
from app.modules.notifications.services import (
    NotificationKind,
    list_notifications_for_recipient,
)
from tests.events.cases import APPROVAL_REASON, REJECTION_REASON

pytestmark = pytest.mark.scrum_31

Decide = Callable[..., EventRequest]
ReloadEventRequest = Callable[[int], EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]

REFERENCE = "EVR-AAAAAAAA"
COORDINATOR_ID = 3
ORGANISER_ID = 7
CHANGE_REASON = "The organiser moved the event to a larger venue."
#: The reason each first decision is given with; a first approval needs none.
FIRST_REASON = {"approved": None, "rejected": REJECTION_REASON}
DECIDED = ["approved", "rejected"]
#: Every first decision, followed by every second one.
DECISION_PAIRS = [
    ("approved", "rejected"),
    ("rejected", "approved"),
    ("approved", "approved"),
    ("rejected", "rejected"),
]
DECISION_PAIR_IDS = [
    "approved-then-rejected",
    "rejected-then-approved",
    "approved-again",
    "rejected-again",
]


@pytest.fixture()
def request_equipment(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
) -> Callable[[], None]:
    """Save an equipment line on ``saved_event_request``, whatever its status."""

    def _request() -> None:
        save(make_equipment_line(saved_event_request, equipment_type))

    return _request


def _assert_decision_locked(decide: Decide) -> None:
    """Try a new decision and check it is refused as locked (AC7)."""
    with pytest.raises(DecisionLockedError) as exc_info:
        decide(COORDINATOR_ID, "rejected", CHANGE_REASON)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "decision_locked")
    assert refused.message == DECISION_LOCKED_MESSAGE


def _decisions_in(history: list[tuple[EventHistoryKind, int | None, Any]]) -> list[Any]:
    """The details of each ``decision_recorded`` entry, oldest first."""
    decisions = []
    for kind, _, details in history:
        if kind is EventHistoryKind.DECISION_RECORDED:
            decisions.append(details)
    return decisions


# --------------------------------------------------------------------------
# AC6 — a decided request can be decided again, with a reason
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("first", "second"), DECISION_PAIRS, ids=DECISION_PAIR_IDS)
def test_a_decided_request_can_be_decided_again_with_a_reason(
    decide: Decide,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
    first: str,
    second: str,
) -> None:
    decide(COORDINATOR_ID, first, FIRST_REASON[first])

    decide(COORDINATOR_ID, second, CHANGE_REASON)

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus(second)


@pytest.mark.parametrize(("first", "second"), DECISION_PAIRS, ids=DECISION_PAIR_IDS)
def test_a_new_decision_requires_a_reason(
    decide: Decide,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
    first: str,
    second: str,
) -> None:
    first_decided = decide(COORDINATOR_ID, first, FIRST_REASON[first])
    status_after_first = first_decided.status

    with pytest.raises(ValidationError) as exc_info:
        decide(COORDINATOR_ID, second)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == {"reason": [REASON_REQUIRED_MESSAGE]}
    assert reload_event_request(saved_event_request.id).status is status_after_first
    assert len(_decisions_in(history_of(saved_event_request.id))) == 1


# --------------------------------------------------------------------------
# AC8 — every decision stays in the history; the latest is current
# --------------------------------------------------------------------------


def test_the_most_recent_decision_is_the_current_one(
    decide: Decide, history_of: HistoryOf, saved_event_request: EventRequest
) -> None:
    decide(COORDINATOR_ID, "approved", APPROVAL_REASON)

    decide(COORDINATOR_ID, "rejected", CHANGE_REASON)

    assert _decisions_in(history_of(saved_event_request.id)) == [
        {"outcome": "approved", "reason": APPROVAL_REASON},
        {"outcome": "rejected", "reason": CHANGE_REASON},
    ]
    decision = get_event_record_for_organiser(ORGANISER_ID, REFERENCE).decision
    assert isinstance(decision, DecisionAsShown)
    assert (decision.outcome, decision.reason, decision.decided_by) == (
        "rejected",
        CHANGE_REASON,
        "Coordinator Three",
    )


# --------------------------------------------------------------------------
# AC7 — no new decision once arrangements exist; the first is never blocked
# --------------------------------------------------------------------------


@pytest.mark.parametrize("first", DECIDED)
def test_a_new_decision_is_not_allowed_once_the_event_has_an_equipment_request(
    decide: Decide,
    request_equipment: Callable[[], None],
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
    first: str,
) -> None:
    first_decided = decide(COORDINATOR_ID, first, FIRST_REASON[first])
    status_after_first = first_decided.status
    request_equipment()

    _assert_decision_locked(decide)

    assert reload_event_request(saved_event_request.id).status is status_after_first
    assert len(_decisions_in(history_of(saved_event_request.id))) == 1


def test_the_lock_is_checked_before_the_payload(
    decide: Decide, request_equipment: Callable[[], None]
) -> None:
    """A decision that can't change says so, whatever the body (ADR-0028)."""
    decide(COORDINATOR_ID, "approved")
    request_equipment()

    with pytest.raises(DecisionLockedError):
        decide_event_request(COORDINATOR_ID, REFERENCE, {})


def test_the_first_decision_is_not_blocked_by_an_equipment_request(
    decide: Decide,
    request_equipment: Callable[[], None],
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    request_equipment()

    decide(COORDINATOR_ID, "approved")

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.APPROVED


# --------------------------------------------------------------------------
# AC10 — the organiser is told of each new decision
# --------------------------------------------------------------------------


def test_the_organiser_is_told_of_each_new_decision(decide: Decide) -> None:
    decide(COORDINATOR_ID, "approved")

    decide(COORDINATOR_ID, "rejected", CHANGE_REASON)

    told = []
    for notification in list_notifications_for_recipient(ORGANISER_ID):
        told.append((notification.kind, notification.detail))
    assert told == [
        (NotificationKind.EVENT_REQUEST_REJECTED, CHANGE_REASON),
        (NotificationKind.EVENT_REQUEST_APPROVED, None),
    ]
