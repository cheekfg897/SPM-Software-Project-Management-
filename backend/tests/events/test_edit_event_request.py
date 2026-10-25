"""Unit tests for SCRUM-33 "Update event information and flag significant changes".

AC1: an assigned coordinator can edit an event's description, programme notes,
accessibility needs and internal planning notes. AC2: a change to a field that could
affect a venue booking or requested equipment is marked significant (reassessment is
in ``test_edit_event_request_reassessment.py``). AC3: preparation details belonging
to Venue Staff and Technical Support Staff (equipment lines, a venue's setup/
turnaround) cannot be edited here; like any field outside the edit, sending one is
refused as an unknown field, not silently ignored. AC4: every change is written to
the event history with who made it and when, in the same commit as the change itself.
Only the request's assigned coordinator may edit it, and only before it is Confirmed:
while it is submitted, under review, awaiting clarification, approved or in Safety
Review (ADR-0101). AC8: a Confirmed event is refused, and the refusal says it changes
only through a change request.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, assigned to Event Coordinator 3), so lookups are real SQL; the
one-commit test uses ``mock_session``. Payload validation (dates, times, notes) is in
``test_edit_event_request_validation.py``; equipment reassessment is in
``test_edit_event_request_reassessment.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    EventEdit,
    RequestNotEditableError,
    get_event_record_for_organiser,
    update_event_request,
)

pytestmark = pytest.mark.scrum_33

MakeEventRequest = Callable[..., EventRequest]
EditEvent = Callable[[int, dict[str, Any] | None], EventEdit]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
ReloadEventRequest = Callable[[int], EventRequest]
SetStatus = Callable[[EventRequestStatus], None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9

#: Every status before Confirmed that a coordinator works in (SCRUM-33's status
#: clarification, ADR-0101), written out so the test doesn't copy the code's own list.
EDITABLE = [
    EventRequestStatus.SUBMITTED,
    EventRequestStatus.UNDER_REVIEW,
    EventRequestStatus.AWAITING_CLARIFICATION,
    EventRequestStatus.APPROVED,
    EventRequestStatus.SAFETY_REVIEW,
]
#: Every other status but Confirmed, which has its own message (AC8), and a draft,
#: which staff never find (ADR-0024). Built from the enum so a status added later is
#: checked too.
REFUSED = [
    status
    for status in EventRequestStatus
    if status not in EDITABLE
    and status is not EventRequestStatus.CONFIRMED
    and status is not EventRequestStatus.DRAFT
]


def _refusal_to_edit(edit_event: EditEvent) -> RequestNotEditableError:
    """The refusal of an edit to the description, which must be refused."""
    with pytest.raises(RequestNotEditableError) as exc_info:
        edit_event(COORDINATOR_ID, {"description": "Revised"})
    return exc_info.value


# --------------------------------------------------------------------------
# AC1 — a note is saved with no further step
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["description", "programme_notes", "accessibility_needs", "internal_planning_notes"]
)
def test_a_note_is_saved_with_no_further_step(
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
    field: str,
) -> None:
    edit = edit_event(COORDINATOR_ID, {field: "Revised"})

    assert getattr(reload_event_request(saved_event_request.id), field) == "Revised"
    assert history_of(saved_event_request.id) == [
        (
            EventHistoryKind.FIELD_CHANGED,
            COORDINATOR_ID,
            {"field": field, "previous_value": None, "new_value": "Revised", "significant": False},
        )
    ]
    assert [(change.field, change.significant) for change in edit.changes] == [(field, False)]


# --------------------------------------------------------------------------
# AC2 — a change to a field that could affect a venue or equipment is significant
# --------------------------------------------------------------------------


SIGNIFICANT_FIELD_CASES = [
    (
        {"proposed_date": "2026-10-20"},
        [
            {
                "field": "proposed_date",
                "previous_value": "2026-10-15",
                "new_value": "2026-10-20",
                "significant": True,
            },
            {
                "field": "end_date",
                "previous_value": "2026-10-15",
                "new_value": "2026-10-20",
                "significant": True,
            },
        ],
    ),
    (
        {"end_date": "2026-10-16"},
        [
            {
                "field": "end_date",
                "previous_value": "2026-10-15",
                "new_value": "2026-10-16",
                "significant": True,
            }
        ],
    ),
    (
        {"start_time": "08:00"},
        [
            {
                "field": "start_time",
                "previous_value": "09:00:00",
                "new_value": "08:00:00",
                "significant": True,
            }
        ],
    ),
    (
        {"end_time": "18:00"},
        [
            {
                "field": "end_time",
                "previous_value": "17:00:00",
                "new_value": "18:00:00",
                "significant": True,
            }
        ],
    ),
    (
        {"expected_attendance": 300},
        [
            {
                "field": "expected_attendance",
                "previous_value": 250,
                "new_value": 300,
                "significant": True,
            }
        ],
    ),
    (
        {"venue_requirements": "Stage needed"},
        [
            {
                "field": "venue_requirements",
                "previous_value": None,
                "new_value": "Stage needed",
                "significant": True,
            }
        ],
    ),
    (
        {"equipment_requirements": "4 projectors"},
        [
            {
                "field": "equipment_requirements",
                "previous_value": None,
                "new_value": "4 projectors",
                "significant": True,
            }
        ],
    ),
]
SIGNIFICANT_FIELD_IDS = [
    "proposed-date-moves-end-date-too",
    "end-date",
    "start-time",
    "end-time",
    "expected-attendance",
    "venue-requirements",
    "equipment-requirements",
]


@pytest.mark.parametrize(
    ("payload", "expected_details"), SIGNIFICANT_FIELD_CASES, ids=SIGNIFICANT_FIELD_IDS
)
def test_a_change_to_a_significant_field_is_marked_significant(
    edit_event: EditEvent,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
    payload: dict[str, Any],
    expected_details: list[dict[str, Any]],
) -> None:
    edit_event(COORDINATOR_ID, payload)

    entries = history_of(saved_event_request.id)
    assert [details for _, _, details in entries] == expected_details
    assert all(
        (kind, actor_id) == (EventHistoryKind.FIELD_CHANGED, COORDINATOR_ID)
        for kind, actor_id, _ in entries
    )


def test_one_edit_can_mix_significant_and_other_changes(
    edit_event: EditEvent, history_of: HistoryOf, saved_event_request: EventRequest
) -> None:
    edit_event(COORDINATOR_ID, {"description": "New", "expected_attendance": 300})

    entries = history_of(saved_event_request.id)
    assert [(details["field"], details["significant"]) for _, _, details in entries if details] == [
        ("description", False),
        ("expected_attendance", True),
    ]


# --------------------------------------------------------------------------
# AC4 — every change is recorded with who made it and when, in one commit
# --------------------------------------------------------------------------


def test_each_change_records_who_made_it_and_when(
    edit_event: EditEvent, saved_event_request: EventRequest, db_session: Session
) -> None:
    before = datetime.now(timezone.utc)

    edit_event(COORDINATOR_ID, {"description": "New", "expected_attendance": 300})

    after = datetime.now(timezone.utc)
    db_session.expire_all()
    stmt = select(EventHistoryEntry).where(
        EventHistoryEntry.event_request_id == saved_event_request.id
    )
    entries = list(db_session.scalars(stmt))
    occurred_at_values = {entry.occurred_at for entry in entries}

    assert len(entries) == 2
    assert len(occurred_at_values) == 1
    assert before <= occurred_at_values.pop() <= after
    assert all(entry.actor_id == COORDINATOR_ID for entry in entries)


def test_the_changes_and_their_history_are_saved_in_one_commit(
    mock_session: MagicMock, make_event_request: MakeEventRequest, today: date
) -> None:
    event_request = make_event_request(coordinator_id=COORDINATOR_ID)
    event_request.id = 1
    # The request, then no safety check in its history (SCRUM-33 AC7).
    mock_session.scalar.side_effect = [event_request, None]
    seen_at_commit: list[tuple[int, list[EventHistoryKind]]] = []

    def note_what_is_saved() -> None:
        added_kinds = [call.args[0].kind for call in mock_session.add.call_args_list]
        seen_at_commit.append((event_request.expected_attendance, added_kinds))

    mock_session.commit.side_effect = note_what_is_saved

    update_event_request(
        COORDINATOR_ID,
        REFERENCE,
        {"description": "New", "expected_attendance": 300},
        session=mock_session,
        today=today,
    )

    assert seen_at_commit == [
        (300, [EventHistoryKind.FIELD_CHANGED, EventHistoryKind.FIELD_CHANGED])
    ]


def test_a_value_equal_to_the_current_one_is_not_a_change(
    edit_event: EditEvent, history_of: HistoryOf, saved_event_request: EventRequest
) -> None:
    edit = edit_event(COORDINATOR_ID, {"expected_attendance": 250})

    assert edit.changes == []
    assert history_of(saved_event_request.id) == []


def test_an_empty_edit_changes_nothing(
    mock_session: MagicMock, make_event_request: MakeEventRequest, today: date
) -> None:
    event_request = make_event_request(coordinator_id=COORDINATOR_ID)
    mock_session.scalar.return_value = event_request

    edit = update_event_request(COORDINATOR_ID, REFERENCE, {}, session=mock_session, today=today)

    assert edit.changes == []
    mock_session.commit.assert_not_called()


def test_the_body_must_be_a_json_object(edit_event: EditEvent) -> None:
    with pytest.raises(ValidationError) as exc_info:
        edit_event(COORDINATOR_ID, None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.message == "Request body must be a JSON object."


# --------------------------------------------------------------------------
# AC3 — preparation details belonging to Venue Staff and Technical Support
# (equipment lines, a venue's setup/turnaround), like any field outside the edit,
# are refused
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "status",
        "reference",
        "name",
        "purpose",
        "registration_required",
        "coordinator_id",
        "equipment_lines",
        "setup_minutes",
        "turnaround_minutes",
    ],
)
def test_fields_outside_the_edit_are_refused(
    edit_event: EditEvent, history_of: HistoryOf, saved_event_request: EventRequest, field: str
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        edit_event(COORDINATOR_ID, {field: "anything"})

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == {field: ["Unknown field."]}
    assert history_of(saved_event_request.id) == []


# --------------------------------------------------------------------------
# ADR-0025 — only the assigned coordinator, only while editable
# --------------------------------------------------------------------------


def test_only_the_events_assigned_coordinator_may_edit_it(
    edit_event: EditEvent, history_of: HistoryOf, saved_event_request: EventRequest
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        edit_event(OTHER_COORDINATOR_ID, {"description": "Revised"})

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert history_of(saved_event_request.id) == []


def test_an_unassigned_event_cannot_be_edited(
    edit_event: EditEvent,
    saved_event_request: EventRequest,
    save: Callable[..., None],
    history_of: HistoryOf,
) -> None:
    saved_event_request.coordinator_id = None
    save(saved_event_request)

    with pytest.raises(NotFoundError) as exc_info:
        edit_event(COORDINATOR_ID, {"description": "Revised"})

    assert exc_info.value.status_code == 404
    assert history_of(saved_event_request.id) == []


def test_an_unknown_reference_is_404(saved_users: list[User], today: date) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        update_event_request(
            COORDINATOR_ID, "EVR-ZZZZZZZZ", {"description": "Revised"}, today=today
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE


def test_the_reference_ignores_case_and_surrounding_spaces(
    saved_event_request: EventRequest, reload_event_request: ReloadEventRequest, today: date
) -> None:
    update_event_request(COORDINATOR_ID, "  evr-aaaaaaaa ", {"description": "Revised"}, today=today)

    assert reload_event_request(saved_event_request.id).description == "Revised"


@pytest.mark.parametrize("status", EDITABLE, ids=lambda status: status.value)
def test_an_event_not_yet_confirmed_can_be_edited_and_keeps_its_status(
    edit_event: EditEvent,
    set_status: SetStatus,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    edit_event(COORDINATOR_ID, {"description": "Revised"})

    reloaded = reload_event_request(saved_event_request.id)
    assert reloaded.description == "Revised"
    assert reloaded.status is status


def test_a_confirmed_event_is_refused_and_pointed_to_a_change_request(
    edit_event: EditEvent,
    set_status: SetStatus,
    history_of: HistoryOf,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    """AC8: a Confirmed event changes only through a change request (SCRUM-56/57)."""
    set_status(EventRequestStatus.CONFIRMED)

    refused = _refusal_to_edit(edit_event)

    assert (refused.status_code, refused.error_code) == (409, "request_not_editable")
    assert refused.message == "A confirmed event can only be changed through a change request."
    assert reload_event_request(saved_event_request.id).description is None
    assert history_of(saved_event_request.id) == []


@pytest.mark.parametrize("status", REFUSED, ids=lambda status: status.value)
def test_a_finished_event_cannot_be_edited(
    edit_event: EditEvent,
    set_status: SetStatus,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    refused = _refusal_to_edit(edit_event)

    assert (refused.status_code, refused.error_code) == (409, "request_not_editable")
    assert refused.message == (
        "An event request can only be edited before it is confirmed, and not once it is "
        "rejected or cancelled."
    )
    assert history_of(saved_event_request.id) == []


def test_a_draft_is_not_found_by_its_coordinator(
    edit_event: EditEvent,
    set_status: SetStatus,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
) -> None:
    """Staff never see a draft (ADR-0024): editing one is a 404, like no request."""
    set_status(EventRequestStatus.DRAFT)

    with pytest.raises(NotFoundError) as exc_info:
        edit_event(COORDINATOR_ID, {"description": "Revised"})

    assert exc_info.value.status_code == 404
    assert history_of(saved_event_request.id) == []


def test_ownership_is_checked_before_status(edit_event: EditEvent, set_status: SetStatus) -> None:
    """A finished event tells another coordinator no more than an open one."""
    set_status(EventRequestStatus.COMPLETED)

    with pytest.raises(NotFoundError) as exc_info:
        edit_event(OTHER_COORDINATOR_ID, {"description": "Revised"})

    assert exc_info.value.status_code == 404


# --------------------------------------------------------------------------
# ADR-0025, ADR-0104 — the organiser's record shows both notes as last saved
# --------------------------------------------------------------------------


def test_the_organiser_sees_the_programme_notes_and_the_planning_notes(
    edit_event: EditEvent,
    saved_event_request: EventRequest,
) -> None:
    """Nothing on the record is hidden from them (SCRUM-24 AC10, SCRUM-33 AC1)."""
    edit_event(
        COORDINATOR_ID,
        {
            "programme_notes": "Doors open at 08:30.",
            "internal_planning_notes": "Reserve the loading dock.",
        },
    )

    record = get_event_record_for_organiser(7, saved_event_request.reference)

    assert record.event_request.programme_notes == "Doors open at 08:30."
    assert record.event_request.internal_planning_notes == "Reserve the loading dock."
