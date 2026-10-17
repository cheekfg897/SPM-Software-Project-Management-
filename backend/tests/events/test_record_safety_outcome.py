"""Unit tests for SCRUM-98 "Record the operational safety check outcome".

AC1: the Safety Officer records Approve, Reject or Request Changes against an event in
Safety Review. AC2, AC3: with a checklist of seven items, each with a note. AC4: a
reason is required for Reject and Request Changes. AC5: an Approve leaves the event in
Safety Review, approved, so SCRUM-49 can confirm it and SCRUM-84/85 can prepare it
(``has_safety_approval``). AC6: Reject and Request Changes return it to planning
(``approved``), never to Rejected. AC7: every outcome is kept in the history with the
officer, the time, the checklist and the reason. AC8: the assigned coordinator is told
the outcome and any reason (ADR-0047).

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, assigned to Event Coordinator 3).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events import services
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.schemas import SAFETY_REASON_REQUIRED_MESSAGE
from app.modules.events.services import (
    ALREADY_SAFETY_APPROVED_MESSAGE,
    NOT_IN_SAFETY_REVIEW_MESSAGE,
    SafetyOutcomeNotAllowedError,
    has_safety_approval,
    list_event_history,
    list_events_awaiting_safety_review,
    record_event_history,
    record_safety_outcome,
)
from app.modules.notifications.services import NotificationKind, list_notifications_for_recipient

pytestmark = pytest.mark.scrum_98

HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
ReloadEventRequest = Callable[[int], EventRequest]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]

REFERENCE = "EVR-AAAAAAAA"
#: A second event in Safety Review, for the tests that one event's outcome is its own.
OTHER_REFERENCE = "EVR-BBBBBBBB"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
SAFETY_OFFICER_ID = 20
#: Everyone saved but the assigned coordinator, the Safety Officer who records the
#: outcome included: only the coordinator is told (AC8).
OTHER_USER_IDS = [9, 4, 7, 5, 2, SAFETY_OFFICER_ID]
RECORDED_AT = datetime(2026, 10, 17, 2, 30, tzinfo=timezone.utc)
REASON = "The fire exit on the east side is blocked by the stage."
#: The seven checklist items of AC2, each with the officer's note.
CHECKLIST = {
    "attendance_vs_capacity": "80 expected in a hall for 300.",
    "venue_layout": "Theatre layout, aisles clear.",
    "emergency_access": "Two exits, both signed.",
    "accessibility": "Step-free entrance confirmed.",
    "equipment_placement": "Projector cables taped down.",
    "crowd_movement": "One-way flow at the doors.",
    "venue_restrictions": "No open flames.",
}
NOT_APPROVED_OUTCOMES = ["rejected", "changes_requested"]
UNKNOWN_OUTCOME_MESSAGE = "Outcome must be approved, rejected or changes_requested."
#: Every status but Safety Review, built from the enum so a status added later is
#: refused here too. A draft is left out: staff can't see one, so it is a 404.
NOT_IN_SAFETY_REVIEW = [
    status
    for status in EventRequestStatus
    if status not in {EventRequestStatus.DRAFT, EventRequestStatus.SAFETY_REVIEW}
]


@pytest.fixture()
def in_review(
    saved_users: list[User],
    saved_event_request: EventRequest,
    make_user: Callable[..., User],
    save: Callable[..., None],
) -> EventRequest:
    """``saved_event_request`` in Safety Review, with a Safety Officer saved."""
    officer = make_user(
        email="safety@example.com", role=Role.SAFETY_OFFICER, user_id=SAFETY_OFFICER_ID
    )
    saved_event_request.status = EventRequestStatus.SAFETY_REVIEW
    save(officer, saved_event_request)
    return saved_event_request


def _record(
    session: Session, outcome: str, reason: str | None = REASON, **changes: Any
) -> EventRequest:
    payload = {"outcome": outcome, "checklist": CHECKLIST, "reason": reason, **changes}
    return record_safety_outcome(
        SAFETY_OFFICER_ID, REFERENCE, payload, session=session, now=RECORDED_AT
    )


def _field_errors(session: Session, outcome: str, **changes: Any) -> dict[str, Any]:
    with pytest.raises(ValidationError) as exc_info:
        _record(session, outcome, **changes)
    return exc_info.value.details


def _refusal(session: Session) -> SafetyOutcomeNotAllowedError:
    with pytest.raises(SafetyOutcomeNotAllowedError) as exc_info:
        _record(session, "approved")
    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "safety_outcome_not_allowed")
    return refused


def _add_history(
    session: Session, event_request: EventRequest, kind: EventHistoryKind, at: datetime
) -> None:
    """Save a history entry of ``kind`` for ``event_request``, by its coordinator."""
    record_event_history(event_request, kind, actor_id=COORDINATOR_ID, session=session, now=at)
    session.commit()


# --------------------------------------------------------------------------
# AC1, AC5, AC6 — each outcome and where it leaves the event
# --------------------------------------------------------------------------


def test_an_approval_leaves_the_event_in_safety_review_and_approved(
    db_session: Session, in_review: EventRequest, reload_event_request: ReloadEventRequest
) -> None:
    assert has_safety_approval(in_review.id, session=db_session) is False

    _record(db_session, "approved", reason=None)

    assert reload_event_request(in_review.id).status is EventRequestStatus.SAFETY_REVIEW
    assert has_safety_approval(in_review.id, session=db_session) is True


@pytest.mark.parametrize("outcome", NOT_APPROVED_OUTCOMES)
def test_reject_and_request_changes_return_the_event_to_planning(
    db_session: Session,
    in_review: EventRequest,
    reload_event_request: ReloadEventRequest,
    outcome: str,
) -> None:
    returned = _record(db_session, outcome)

    assert returned.status is EventRequestStatus.APPROVED
    assert reload_event_request(in_review.id).status is EventRequestStatus.APPROVED
    assert has_safety_approval(in_review.id, session=db_session) is False


def test_an_approval_is_void_once_the_event_is_sent_for_review_again(
    db_session: Session, in_review: EventRequest
) -> None:
    _record(db_session, "approved")

    _add_history(
        db_session,
        in_review,
        EventHistoryKind.SAFETY_REVIEW_REQUESTED,
        RECORDED_AT + timedelta(hours=1),
    )

    assert has_safety_approval(in_review.id, session=db_session) is False


def test_a_later_entry_of_another_kind_leaves_the_approval_in_place(
    db_session: Session, in_review: EventRequest
) -> None:
    """Only a new request for review voids an approval, not any newer entry."""
    _record(db_session, "approved")

    _add_history(
        db_session,
        in_review,
        EventHistoryKind.COORDINATOR_REASSIGNED,
        RECORDED_AT + timedelta(hours=1),
    )

    assert has_safety_approval(in_review.id, session=db_session) is True


def test_the_newest_entry_decides_whatever_order_they_were_saved_in(
    db_session: Session, in_review: EventRequest
) -> None:
    """The request for review is saved first but happened after the approval."""
    _add_history(
        db_session,
        in_review,
        EventHistoryKind.SAFETY_REVIEW_REQUESTED,
        RECORDED_AT + timedelta(hours=1),
    )

    _record(db_session, "approved")

    assert has_safety_approval(in_review.id, session=db_session) is False


def test_of_two_entries_at_the_same_instant_the_one_saved_last_decides(
    db_session: Session, in_review: EventRequest
) -> None:
    _add_history(db_session, in_review, EventHistoryKind.SAFETY_REVIEW_REQUESTED, RECORDED_AT)

    _record(db_session, "approved")

    assert has_safety_approval(in_review.id, session=db_session) is True


def test_another_events_approval_does_not_count_for_this_one(
    db_session: Session,
    in_review: EventRequest,
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
) -> None:
    other = make_event_request(
        reference=OTHER_REFERENCE, status=EventRequestStatus.SAFETY_REVIEW, coordinator_id=9
    )
    save(other)

    record_safety_outcome(
        SAFETY_OFFICER_ID,
        OTHER_REFERENCE,
        {"outcome": "approved", "checklist": CHECKLIST},
        session=db_session,
        now=RECORDED_AT,
    )

    assert has_safety_approval(in_review.id, session=db_session) is False
    waiting = list_events_awaiting_safety_review(session=db_session)
    assert [event.event_request.reference for event in waiting] == [REFERENCE]


def test_an_approved_event_leaves_the_safety_officers_list(
    db_session: Session, in_review: EventRequest
) -> None:
    assert len(list_events_awaiting_safety_review(session=db_session)) == 1

    _record(db_session, "approved")

    assert list_events_awaiting_safety_review(session=db_session) == []


# --------------------------------------------------------------------------
# AC2, AC3, AC4 — the checklist and the reason
# --------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", NOT_APPROVED_OUTCOMES)
def test_a_reason_is_required_to_reject_or_request_changes(
    db_session: Session, in_review: EventRequest, outcome: str
) -> None:
    errors = _field_errors(db_session, outcome, reason=None)

    assert errors == {"reason": [SAFETY_REASON_REQUIRED_MESSAGE]}


@pytest.mark.parametrize("item", sorted(CHECKLIST))
def test_every_checklist_item_needs_a_note(
    db_session: Session, in_review: EventRequest, item: str
) -> None:
    checklist = {**CHECKLIST}
    del checklist[item]

    errors = _field_errors(db_session, "approved", checklist=checklist)

    assert list(errors["checklist"]) == [item]


@pytest.mark.parametrize("item", sorted(CHECKLIST))
def test_a_blank_checklist_note_is_refused(
    db_session: Session, in_review: EventRequest, item: str
) -> None:
    errors = _field_errors(db_session, "approved", checklist={**CHECKLIST, item: "  "})

    assert errors == {"checklist": {item: ["Must not be blank."]}}


@pytest.mark.parametrize(
    ("payload", "details"),
    [
        (
            {"checklist": CHECKLIST},
            {"outcome": ["Missing data for required field."]},
        ),
        (
            {"outcome": "maybe", "checklist": CHECKLIST},
            {"outcome": [UNKNOWN_OUTCOME_MESSAGE]},
        ),
        (
            {"outcome": True, "checklist": CHECKLIST},
            {"outcome": [UNKNOWN_OUTCOME_MESSAGE]},
        ),
        (
            {"outcome": "rejected", "reason": REASON},
            {"checklist": ["Missing data for required field."]},
        ),
        (
            {"outcome": "rejected", "checklist": ["No notes."], "reason": REASON},
            {"checklist": {"_schema": ["Invalid input type."]}},
        ),
        (
            {
                "outcome": "rejected",
                "checklist": {**CHECKLIST, "venue_layout": 5},
                "reason": REASON,
            },
            {"checklist": {"venue_layout": ["Not a valid string."]}},
        ),
        (
            {
                "outcome": "rejected",
                "checklist": {**CHECKLIST, "fire_drill": "Done."},
                "reason": REASON,
            },
            {"checklist": {"fire_drill": ["Unknown field."]}},
        ),
        (
            {"outcome": "rejected", "checklist": CHECKLIST, "reason": "   "},
            {"reason": ["Must not be blank."]},
        ),
        (
            {"outcome": "rejected", "checklist": CHECKLIST, "reason": 5},
            {"reason": ["Not a valid string."]},
        ),
        (
            {"outcome": "approved", "checklist": CHECKLIST, "status": "confirmed"},
            {"status": ["Unknown field."]},
        ),
    ],
    ids=[
        "no-outcome",
        "unknown-outcome",
        "outcome-a-boolean",
        "no-checklist",
        "checklist-a-list",
        "note-a-number",
        "unknown-checklist-item",
        "blank-reason",
        "reason-a-number",
        "status-sent",
    ],
)
def test_an_invalid_payload_is_refused_and_nothing_is_recorded(
    db_session: Session,
    in_review: EventRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    payload: dict[str, Any],
    details: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        record_safety_outcome(SAFETY_OFFICER_ID, REFERENCE, payload, session=db_session)

    assert exc_info.value.details == details
    assert reload_event_request(in_review.id).status is EventRequestStatus.SAFETY_REVIEW
    assert history_of(in_review.id) == []


def test_the_notes_and_the_reason_are_trimmed(
    db_session: Session, in_review: EventRequest, history_of: HistoryOf
) -> None:
    padded_checklist = {}
    for item, note in CHECKLIST.items():
        padded_checklist[item] = f"  {note}\n"

    _record(db_session, "rejected", reason=f"  {REASON}\n", checklist=padded_checklist)

    [(_, _, details)] = history_of(in_review.id)
    assert details == {"outcome": "rejected", "checklist": CHECKLIST, "reason": REASON}


# --------------------------------------------------------------------------
# AC7 — every outcome is kept in the history
# --------------------------------------------------------------------------


def test_the_outcome_is_kept_in_the_history_with_the_officer_checklist_and_reason(
    db_session: Session, in_review: EventRequest, history_of: HistoryOf
) -> None:
    _record(db_session, "changes_requested")

    assert history_of(in_review.id) == [
        (
            EventHistoryKind.SAFETY_OUTCOME_RECORDED,
            SAFETY_OFFICER_ID,
            {"outcome": "changes_requested", "checklist": CHECKLIST, "reason": REASON},
        )
    ]
    entry = db_session.scalar(select(EventHistoryEntry))
    assert entry.occurred_at.astimezone(timezone.utc) == RECORDED_AT


def test_only_internal_staff_see_the_outcome_in_the_history(
    db_session: Session, in_review: EventRequest
) -> None:
    """The checklist is the Safety Officer's working: internal-only (ADR-0047 #19)."""
    _record(db_session, "changes_requested")

    seen_by_coordinator = list_event_history(
        COORDINATOR_ID, REFERENCE, viewer_role=Role.EVENT_COORDINATOR, session=db_session
    )
    seen_by_organiser = list_event_history(
        in_review.organiser_id, REFERENCE, viewer_role=Role.EVENT_ORGANISER, session=db_session
    )

    assert [entry.kind for entry in seen_by_coordinator] == [
        EventHistoryKind.SAFETY_OUTCOME_RECORDED
    ]
    assert seen_by_organiser == []


# --------------------------------------------------------------------------
# AC1 — only an event in Safety Review, and only once approved
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", NOT_IN_SAFETY_REVIEW, ids=lambda status: status.value)
def test_only_an_event_in_safety_review_can_get_an_outcome(
    db_session: Session,
    in_review: EventRequest,
    save: Callable[..., None],
    history_of: HistoryOf,
    status: EventRequestStatus,
) -> None:
    in_review.status = status
    save(in_review)

    refused = _refusal(db_session)

    assert refused.message == NOT_IN_SAFETY_REVIEW_MESSAGE
    assert history_of(in_review.id) == []


def test_an_approved_event_cannot_get_another_outcome(
    db_session: Session, in_review: EventRequest
) -> None:
    _record(db_session, "approved")

    refused = _refusal(db_session)

    assert refused.message == ALREADY_SAFETY_APPROVED_MESSAGE


def test_an_unknown_event_is_not_found(db_session: Session, in_review: EventRequest) -> None:
    with pytest.raises(NotFoundError):
        record_safety_outcome(
            SAFETY_OFFICER_ID,
            "EVR-ZZZZZZZZ",
            {"outcome": "approved", "checklist": CHECKLIST},
            session=db_session,
        )


# --------------------------------------------------------------------------
# AC8 — the assigned coordinator is told the outcome and any reason
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "kind"),
    [
        ("approved", NotificationKind.SAFETY_CHECK_APPROVED),
        ("rejected", NotificationKind.SAFETY_CHECK_REJECTED),
        ("changes_requested", NotificationKind.SAFETY_CHANGES_REQUESTED),
    ],
)
def test_the_assigned_coordinator_is_told_the_outcome_and_reason(
    db_session: Session,
    in_review: EventRequest,
    notifications_of: NotificationsOf,
    outcome: str,
    kind: NotificationKind,
) -> None:
    _record(db_session, outcome)

    unread = None
    assert notifications_of(COORDINATOR_ID) == [
        (in_review.id, REFERENCE, in_review.name, kind, unread)
    ]
    [notice] = list_notifications_for_recipient(COORDINATOR_ID)
    assert notice.detail == REASON
    for user_id in OTHER_USER_IDS:
        assert notifications_of(user_id) == []


def test_the_outcome_is_saved_even_if_the_notice_is_not(
    db_session: Session,
    in_review: EventRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The outcome is committed before the notice is written (ADR-0015)."""

    def _lost_connection(*_: Any, **__: Any) -> None:
        raise OperationalError("INSERT INTO notifications ...", {}, Exception("gone"))

    monkeypatch.setattr(services, "notify_users", _lost_connection)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        returned = _record(db_session, "rejected")

    assert returned.status is EventRequestStatus.APPROVED
    assert reload_event_request(in_review.id).status is EventRequestStatus.APPROVED
    assert [kind for kind, _, _ in history_of(in_review.id)] == [
        EventHistoryKind.SAFETY_OUTCOME_RECORDED
    ]
    assert [record.getMessage() for record in caplog.records] == [
        "event_request_notification_failed reference=EVR-AAAAAAAA kind=safety_check_rejected"
    ]
