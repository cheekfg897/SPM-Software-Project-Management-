"""Unit tests for SCRUM-32 "Ask the Organiser for clarification": the resubmit payload.

AC2: the body holds a required ``response`` and, optionally, amendments to any field
the organiser filled in on submission. Each amended field is checked as it is on
submission (ADR-0001, ADR-0002, ADR-0003), with the time window checked against the
request's saved values where a field is left out, as on an edit (ADR-0025). Nothing
submission requires can be cleared. The coordinator's notes and the fields the server
controls are unknown fields (ADR-0029).

Runs against ``db_session`` with ``saved_users`` and ``awaiting_clarification_request``
(``EVR-AAAAAAAA``, proposed 2026-10-15 09:00-17:00, ``today`` 2026-09-15). Every
rejection leaves the request's status and its history untouched.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from app.common.errors import ValidationError
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from tests.events.cases import (
    CLARIFICATION_RESPONSE,
    FIELD_REJECTED_CASES,
    WINDOW_VIOLATION_IDS,
    WINDOW_VIOLATIONS,
)

pytestmark = pytest.mark.scrum_32

Resubmit = Callable[[int, Any], EventRequest]
ReloadEventRequest = Callable[[int], EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
AssertStatusUnchanged = Callable[[EventRequestStatus], None]

ORGANISER_ID = 7
ANSWER = {"response": CLARIFICATION_RESPONSE}


def _assert_refused(
    resubmit: Resubmit,
    assert_status_unchanged: AssertStatusUnchanged,
    payload: Any,
    details: dict[str, list[str]],
) -> None:
    """Resubmitting ``payload`` is a 400 with ``details``, and changes nothing."""
    with pytest.raises(ValidationError) as exc_info:
        resubmit(ORGANISER_ID, payload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == details
    assert_status_unchanged(EventRequestStatus.AWAITING_CLARIFICATION)


# --------------------------------------------------------------------------
# AC2 — a response is required
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "details"),
    [
        ({}, {"response": ["Missing data for required field."]}),
        ({"response": ""}, {"response": ["Must not be blank."]}),
        ({"response": "   "}, {"response": ["Must not be blank."]}),
        ({"response": None}, {"response": ["Field may not be null."]}),
        ({"response": 5}, {"response": ["Not a valid string."]}),
        ({"expected_attendance": 300}, {"response": ["Missing data for required field."]}),
    ],
    ids=["missing", "empty", "spaces", "null", "a-number", "amendments-only"],
)
def test_a_response_is_required(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
    payload: dict[str, Any],
    details: dict[str, list[str]],
) -> None:
    _assert_refused(resubmit, assert_status_unchanged, payload, details)


def test_the_response_is_trimmed(
    resubmit: Resubmit, history_of: HistoryOf, awaiting_clarification_request: EventRequest
) -> None:
    resubmit(ORGANISER_ID, {"response": f"\n {CLARIFICATION_RESPONSE}  "})

    assert history_of(awaiting_clarification_request.id) == [
        (EventHistoryKind.CLARIFICATION_ANSWERED, ORGANISER_ID, ANSWER)
    ]


def test_amended_text_is_trimmed_and_a_blank_one_is_cleared(
    resubmit: Resubmit,
    reload_event_request: ReloadEventRequest,
    awaiting_clarification_request: EventRequest,
    save: Callable[..., None],
) -> None:
    """The submission's own trimming still runs beside the response's (ADR-0024)."""
    awaiting_clarification_request.purpose = "Annual showcase"
    save(awaiting_clarification_request)

    resubmit(ORGANISER_ID, {**ANSWER, "name": "  Partner Day ", "purpose": "   "})

    reloaded = reload_event_request(awaiting_clarification_request.id)
    assert (reloaded.name, reloaded.purpose) == ("Partner Day", None)


# --------------------------------------------------------------------------
# ADR-0001, ADR-0002, ADR-0003 — each amendment is checked as on submission
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("field", "value"), FIELD_REJECTED_CASES)
def test_every_amended_field_is_checked_as_on_submission(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
    field: str,
    value: Any,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        resubmit(ORGANISER_ID, {**ANSWER, field: value})

    assert exc_info.value.status_code == 400
    assert field in (exc_info.value.details or {})
    assert_status_unchanged(EventRequestStatus.AWAITING_CLARIFICATION)


def test_a_past_proposed_date_is_refused(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    payload = {**ANSWER, "proposed_date": "2026-09-14"}

    _assert_refused(
        resubmit,
        assert_status_unchanged,
        payload,
        {"proposed_date": ["Proposed date cannot be in the past."]},
    )


@pytest.mark.parametrize(("amendment", "details"), WINDOW_VIOLATIONS, ids=WINDOW_VIOLATION_IDS)
def test_the_window_is_checked_against_the_saved_values(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
    amendment: dict[str, Any],
    details: dict[str, list[str]],
) -> None:
    _assert_refused(resubmit, assert_status_unchanged, {**ANSWER, **amendment}, details)


def test_moving_the_date_moves_the_end_date_with_it(
    resubmit: Resubmit,
    reload_event_request: ReloadEventRequest,
    awaiting_clarification_request: EventRequest,
    save: Callable[..., None],
) -> None:
    awaiting_clarification_request.end_date = date(2026, 10, 16)
    save(awaiting_clarification_request)

    resubmit(ORGANISER_ID, {**ANSWER, "proposed_date": "2026-10-20"})

    reloaded = reload_event_request(awaiting_clarification_request.id)
    assert (reloaded.proposed_date, reloaded.end_date) == (date(2026, 10, 20), date(2026, 10, 21))


# --------------------------------------------------------------------------
# ADR-0029 — nothing submission requires can be cleared; nothing else can be sent
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "message"),
    [("", "Event name must not be blank."), (None, "Field may not be null.")],
    ids=["blank", "null"],
)
def test_the_name_cannot_be_cleared(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
    value: str | None,
    message: str,
) -> None:
    _assert_refused(
        resubmit, assert_status_unchanged, {**ANSWER, "name": value}, {"name": [message]}
    )


@pytest.mark.parametrize(
    "field", ["proposed_date", "end_date", "start_time", "end_time", "expected_attendance"]
)
def test_a_detail_cannot_be_cleared(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
    field: str,
) -> None:
    _assert_refused(
        resubmit,
        assert_status_unchanged,
        {**ANSWER, field: None},
        {field: ["Field may not be null."]},
    )


@pytest.mark.parametrize(
    "field",
    [
        "programme_notes",
        "internal_planning_notes",
        "status",
        "reference",
        "organiser_id",
        "coordinator_id",
    ],
)
def test_the_coordinators_notes_and_server_fields_are_refused(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
    field: str,
) -> None:
    _assert_refused(
        resubmit, assert_status_unchanged, {**ANSWER, field: "x"}, {field: ["Unknown field."]}
    )


def test_the_body_must_be_a_json_object(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        resubmit(ORGANISER_ID, [CLARIFICATION_RESPONSE])

    assert exc_info.value.message == "Request body must be a JSON object."
    assert_status_unchanged(EventRequestStatus.AWAITING_CLARIFICATION)
