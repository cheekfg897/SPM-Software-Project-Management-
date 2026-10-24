"""Unit tests for SCRUM-33 "Update event information and flag significant changes".

AC7: once the event has passed its Operational Safety Check, a significant change
withdraws the safety approval, and the event must pass a new check before it can be
confirmed or prepared. A Confirmed event can't be edited directly (AC8), so the
approval an edit withdraws is one given in Safety Review: the event goes back to
Approved, from where the coordinator can send it to Safety Review again (ADR-0087,
ADR-0101). The withdrawal is a ``safety_approval_withdrawn`` history entry by the
coordinator, naming the significant fields, which internal staff see and the
organiser does not. A change that isn't significant, or an event without an
approval, withdraws nothing.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, organiser 7, assigned to Event Coordinator 3), so
``has_safety_approval`` reads the history the edit wrote.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.schemas import EditEventRequestSchema
from app.modules.events.services import (
    SIGNIFICANT_FIELDS,
    EventEdit,
    has_safety_approval,
    list_event_history,
)

pytestmark = pytest.mark.scrum_33

EditEvent = Callable[[int, dict[str, Any] | None], EventEdit]
WithdrawalsOf = Callable[[int], list[tuple[int | None, dict[str, Any] | None]]]
ReloadEventRequest = Callable[[int], EventRequest]
ApprovedForSafety = Callable[[EventRequestStatus], EventRequest]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
#: The Event Organiser whose organisation ``saved_event_request`` belongs to.
ORGANISER_ID = 7
WITHDRAWN = EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN

#: One changed value for each significant field, written out (ADR-0025), and the
#: fields the withdrawal names: a new proposed date moves the end date with it.
#: ``saved_event_request`` runs 2026-10-15, 09:00-17:00, for 250 people.
SIGNIFICANT_CHANGES = [
    ({"proposed_date": "2026-10-20"}, ["proposed_date", "end_date"]),
    ({"end_date": "2026-10-16"}, ["end_date"]),
    ({"start_time": "08:00"}, ["start_time"]),
    ({"end_time": "18:00"}, ["end_time"]),
    ({"expected_attendance": 300}, ["expected_attendance"]),
    ({"venue_requirements": "Stage needed"}, ["venue_requirements"]),
    ({"equipment_requirements": "4 mics"}, ["equipment_requirements"]),
]
#: The editable fields that aren't significant: the notes (AC1).
NOTE_FIELDS = ["description", "programme_notes", "accessibility_needs", "internal_planning_notes"]


# --------------------------------------------------------------------------
# AC7 — a significant change withdraws the approval
# --------------------------------------------------------------------------


def test_the_cases_cover_every_editable_field() -> None:
    """A field made editable or significant later needs a case here."""
    significant = {field for payload, _ in SIGNIFICANT_CHANGES for field in payload}

    assert significant == SIGNIFICANT_FIELDS
    assert sorted([*significant, *NOTE_FIELDS]) == sorted(EditEventRequestSchema.Meta.fields)


@pytest.mark.parametrize(
    ("payload", "significant_fields"),
    [
        *SIGNIFICANT_CHANGES,
        (
            {"description": "New notes", "expected_attendance": 300, "end_time": "18:00"},
            ["end_time", "expected_attendance"],
        ),
    ],
    ids=[*(next(iter(payload)) for payload, _ in SIGNIFICANT_CHANGES), "only-the-significant"],
)
def test_a_significant_change_withdraws_the_safety_approval(
    approved_for_safety: ApprovedForSafety,
    edit_event: EditEvent,
    safety_withdrawals_of: WithdrawalsOf,
    payload: dict[str, Any],
    significant_fields: list[str],
) -> None:
    event = approved_for_safety(EventRequestStatus.SAFETY_REVIEW)

    edit_event(COORDINATOR_ID, payload)

    assert has_safety_approval(event.id) is False
    assert safety_withdrawals_of(event.id) == [
        (COORDINATOR_ID, {"significant_fields": significant_fields})
    ]


def test_an_event_in_safety_review_goes_back_to_approved_for_a_new_safety_check(
    approved_for_safety: ApprovedForSafety,
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
) -> None:
    event = approved_for_safety(EventRequestStatus.SAFETY_REVIEW)

    edit = edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    assert edit.event_request.status is EventRequestStatus.APPROVED
    assert reload_event_request(event.id).status is EventRequestStatus.APPROVED


def test_an_approved_event_with_an_approval_loses_it_and_stays_approved(
    approved_for_safety: ApprovedForSafety,
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
) -> None:
    """Flagged while Confirmed, it went back to Approved, approval kept (ADR-0053)."""
    event = approved_for_safety(EventRequestStatus.APPROVED)

    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    assert has_safety_approval(event.id) is False
    assert reload_event_request(event.id).status is EventRequestStatus.APPROVED


# --------------------------------------------------------------------------
# AC7 — nothing to withdraw
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        *({field: "New notes"} for field in NOTE_FIELDS),
        {"expected_attendance": 250},
        {"description": "New notes", "expected_attendance": 250, "start_time": "09:00"},
    ],
    ids=[*NOTE_FIELDS, "same-attendance-sent-again", "a-note-and-same-timing-sent-again"],
)
def test_a_change_that_is_not_significant_keeps_the_safety_approval(
    approved_for_safety: ApprovedForSafety,
    edit_event: EditEvent,
    safety_withdrawals_of: WithdrawalsOf,
    reload_event_request: ReloadEventRequest,
    payload: dict[str, Any],
) -> None:
    """A note, or a significant field sent with the value it already has (ADR-0025)."""
    event = approved_for_safety(EventRequestStatus.SAFETY_REVIEW)

    edit_event(COORDINATOR_ID, payload)

    assert has_safety_approval(event.id) is True
    assert safety_withdrawals_of(event.id) == []
    assert reload_event_request(event.id).status is EventRequestStatus.SAFETY_REVIEW


def test_an_event_without_a_safety_approval_has_nothing_withdrawn(
    saved_users: list[User],
    saved_event_request: EventRequest,
    save: Callable[..., None],
    edit_event: EditEvent,
    safety_withdrawals_of: WithdrawalsOf,
    reload_event_request: ReloadEventRequest,
) -> None:
    """Still waiting for the Safety Officer, who checks the event as it now stands."""
    saved_event_request.status = EventRequestStatus.SAFETY_REVIEW
    save(saved_event_request)

    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    assert safety_withdrawals_of(saved_event_request.id) == []
    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.SAFETY_REVIEW


# --------------------------------------------------------------------------
# AC5 — the withdrawal is for internal eyes only
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("viewer_id", "viewer_role", "sees_it"),
    [
        (COORDINATOR_ID, Role.EVENT_COORDINATOR, True),
        (ORGANISER_ID, Role.EVENT_ORGANISER, False),
    ],
    ids=["the-coordinator", "the-organiser"],
)
def test_only_internal_staff_see_the_withdrawal(
    approved_for_safety: ApprovedForSafety,
    edit_event: EditEvent,
    viewer_id: int,
    viewer_role: Role,
    sees_it: bool,
) -> None:
    approved_for_safety(EventRequestStatus.SAFETY_REVIEW)
    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    history = list_event_history(viewer_id, REFERENCE, viewer_role=viewer_role)

    kinds = [entry.kind for entry in history]
    assert EventHistoryKind.FIELD_CHANGED in kinds
    assert (WITHDRAWN in kinds) is sees_it
