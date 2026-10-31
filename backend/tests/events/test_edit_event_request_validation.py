"""Unit tests for SCRUM-33 "Update event information and flag significant changes".

Payload validation for ``update_event_request``: the same attendance, date and time
rules as submitting (ADR-0001, ADR-0002, ADR-0003), but checked against the merged
value of a sent field and the request's current one (ADR-0025), plus how notes are
trimmed and cleared. AC1-AC4 and unknown-field rejection (AC3) are in
``test_edit_event_request.py``.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, proposed 2026-10-15 09:00-17:00, assigned to Event Coordinator 3).
Every rejection leaves the request and its history untouched.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from app.common.errors import ValidationError
from app.modules.events.models import EventHistoryKind, EventRequest
from app.modules.events.services import EventEdit
from tests.events.cases import WINDOW_VIOLATION_IDS, WINDOW_VIOLATIONS

#: Each test edits an approved event, the first status a direct edit is allowed in
#: (SCRUM-110).
pytestmark = [pytest.mark.scrum_33, pytest.mark.usefixtures("approved_event_request")]

EditEvent = Callable[[int, dict[str, Any] | None], EventEdit]
ReloadEventRequest = Callable[[int], EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]

COORDINATOR_ID = 3


# --------------------------------------------------------------------------
# ADR-0003 — expected attendance is a whole number of at least 1
# --------------------------------------------------------------------------


ATTENDANCE_REJECTIONS = [
    (0, {"expected_attendance": ["Expected attendance must be at least 1."]}),
    (True, {"expected_attendance": ["Not a valid integer."]}),
    (None, {"expected_attendance": ["Field may not be null."]}),
]


@pytest.mark.parametrize(
    ("attendance", "expected_details"), ATTENDANCE_REJECTIONS, ids=["zero", "boolean", "null"]
)
def test_attendance_must_be_a_whole_number_of_at_least_one(
    edit_event: EditEvent,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
    attendance: Any,
    expected_details: dict[str, list[str]],
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        edit_event(COORDINATOR_ID, {"expected_attendance": attendance})

    assert exc_info.value.details == expected_details
    assert history_of(saved_event_request.id) == []


# --------------------------------------------------------------------------
# ADR-0001 — a sent proposed date cannot be in the past
# --------------------------------------------------------------------------


def test_a_proposed_date_in_the_past_is_rejected(
    edit_event: EditEvent, history_of: HistoryOf, saved_event_request: EventRequest
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        edit_event(COORDINATOR_ID, {"proposed_date": "2026-09-14"})

    assert exc_info.value.details == {"proposed_date": ["Proposed date cannot be in the past."]}
    assert history_of(saved_event_request.id) == []


def test_a_proposed_date_of_today_is_accepted(
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    edit_event(COORDINATOR_ID, {"proposed_date": "2026-09-15"})

    assert reload_event_request(saved_event_request.id).proposed_date == date(2026, 9, 15)


# --------------------------------------------------------------------------
# ADR-0002 — a sent time carries no timezone offset
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["start_time", "end_time"])
def test_a_time_with_a_timezone_offset_is_rejected(
    edit_event: EditEvent, history_of: HistoryOf, saved_event_request: EventRequest, field: str
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        edit_event(COORDINATOR_ID, {field: "12:00:00+08:00"})

    assert exc_info.value.details == {field: ["Time must not include a timezone offset."]}
    assert history_of(saved_event_request.id) == []


# --------------------------------------------------------------------------
# ADR-0002 — the window is checked on the merged values, not only what was sent
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "expected_details"), WINDOW_VIOLATIONS, ids=WINDOW_VIOLATION_IDS
)
def test_the_merged_time_window_is_checked(
    edit_event: EditEvent,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
    payload: dict[str, Any],
    expected_details: dict[str, list[str]],
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        edit_event(COORDINATOR_ID, payload)

    assert exc_info.value.details == expected_details
    assert history_of(saved_event_request.id) == []


def test_moving_an_overnight_event_keeps_its_length(
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
    save: Callable[..., None],
) -> None:
    saved_event_request.end_date = date(2026, 10, 16)
    save(saved_event_request)

    edit_event(COORDINATOR_ID, {"proposed_date": "2026-10-20"})

    reloaded = reload_event_request(saved_event_request.id)
    assert (reloaded.proposed_date, reloaded.end_date) == (date(2026, 10, 20), date(2026, 10, 21))


def test_an_end_date_sent_with_a_new_proposed_date_is_kept(
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    edit_event(COORDINATOR_ID, {"proposed_date": "2026-10-20", "end_date": "2026-10-22"})

    reloaded = reload_event_request(saved_event_request.id)
    assert (reloaded.proposed_date, reloaded.end_date) == (date(2026, 10, 20), date(2026, 10, 22))


# --------------------------------------------------------------------------
# Notes: trimmed, and cleared by a blank string or null
# --------------------------------------------------------------------------


def test_notes_are_trimmed(
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    edit_event(COORDINATOR_ID, {"description": "  Revised  "})

    assert reload_event_request(saved_event_request.id).description == "Revised"


def test_a_blank_note_is_cleared(
    edit_event: EditEvent,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
    save: Callable[..., None],
) -> None:
    saved_event_request.description = "Old"
    save(saved_event_request)

    edit_event(COORDINATOR_ID, {"description": "   "})

    assert history_of(saved_event_request.id) == [
        (
            EventHistoryKind.FIELD_CHANGED,
            COORDINATOR_ID,
            {
                "field": "description",
                "previous_value": "Old",
                "new_value": None,
                "significant": False,
            },
        )
    ]


def test_null_clears_a_note(
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
    save: Callable[..., None],
) -> None:
    saved_event_request.description = "Old"
    save(saved_event_request)

    edit_event(COORDINATOR_ID, {"description": None})

    assert reload_event_request(saved_event_request.id).description is None


# --------------------------------------------------------------------------
# ADR-0025 — a field that isn't sent is left exactly as it was
# --------------------------------------------------------------------------


def test_fields_not_sent_are_left_alone(
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
    save: Callable[..., None],
) -> None:
    """Regression: an edit schema must not reuse submit's ``load_default=None``."""
    saved_event_request.accessibility_needs = "Step-free access"
    save(saved_event_request)

    edit_event(COORDINATOR_ID, {"description": "Revised"})

    assert reload_event_request(saved_event_request.id).accessibility_needs == "Step-free access"
