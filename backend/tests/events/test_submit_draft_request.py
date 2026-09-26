"""Unit tests for SCRUM-20 "Save and resume a draft event request" — submitting a draft.

Submitting a draft runs it back through SCRUM-19's own rules (ADR-0001 to ADR-0003,
ADR-0024): a detail the draft never got, or one that fails a rule, is reported
exactly as ``POST /requests`` reports it, and nothing is saved unless every rule
passes. A submitted draft keeps its reference (ADR-0004), is assigned to the
least-loaded Event Coordinator with its assignment recorded and notified, exactly as
a fresh submission is (SCRUM-30 AC1, AC2, ADR-0018), and becomes visible to the
organiser's colleagues once it is no longer a draft (SCRUM-7, ADR-0024).

Runs against ``db_session`` with ``saved_users``: organiser 7 in client organisation
3, Event Coordinators 3 and 9 (both unloaded, so 3 is least-loaded on a tie).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import (
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    NOT_A_DRAFT_MESSAGE,
    RequestNotDraftError,
    list_event_requests_for_organiser,
    submit_draft_event_request,
)
from tests.events.cases import DRAFT_REFERENCE

pytestmark = pytest.mark.scrum_20

ORGANISER_ID = 7
COLLEAGUE_ID = 8

SaveDraft = Callable[[int, dict[str, Any]], EventRequest]
ReloadEventRequest = Callable[[int], EventRequest]

#: A draft with every field a submission needs.
COMPLETE_DRAFT_PAYLOAD = {
    "name": "Partner Summit",
    "proposed_date": "2026-10-15",
    "start_time": "09:00",
    "end_time": "17:00",
    "expected_attendance": 250,
}

#: A detail submission requires that the draft was never given.
INCOMPLETE_DETAIL_FIELDS = ["proposed_date", "start_time", "end_time", "expected_attendance"]

#: A complete draft made to fail one submission rule: (extra fields, field, message).
RULE_BREAKING_CASES = [
    pytest.param(
        {"proposed_date": "2020-01-01"},
        "proposed_date",
        "Proposed date cannot be in the past.",
        id="past_date",
    ),
    pytest.param(
        {"start_time": "14:00", "end_time": "13:00"},
        "end_time",
        "Event must end after it starts.",
        id="ends_before_it_starts",
    ),
    pytest.param(
        {"end_date": "2026-10-14"},
        "end_date",
        "End date cannot be before the proposed date.",
        id="end_date_before_proposed_date",
    ),
]


#: When a draft was first saved: weeks before it is submitted, so a reset would show.
FIRST_SAVED_AT = datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc)


def _submit(reference: str, session: Session, today: date) -> EventRequest:
    """Submit ``reference`` as organiser 7 on ``session``, pinned to ``today``."""
    return submit_draft_event_request(ORGANISER_ID, reference, session=session, today=today)


# --------------------------------------------------------------------------
# A complete draft is submitted under the full submission rules
# --------------------------------------------------------------------------


def test_a_complete_draft_is_submitted_under_its_own_reference(
    saved_users: list[User],
    save_draft: SaveDraft,
    reload_event_request: ReloadEventRequest,
    db_session: Session,
    today: date,
) -> None:
    draft = save_draft(ORGANISER_ID, COMPLETE_DRAFT_PAYLOAD)

    submitted = _submit(DRAFT_REFERENCE, db_session, today)

    assert submitted.id == draft.id
    assert submitted.reference == DRAFT_REFERENCE
    reloaded = reload_event_request(draft.id)
    assert reloaded.status is EventRequestStatus.SUBMITTED
    assert reloaded.name == "Partner Summit"
    assert reloaded.proposed_date == date(2026, 10, 15)


def test_a_submitted_draft_keeps_when_it_was_first_saved(
    saved_users: list[User],
    save_draft: SaveDraft,
    reload_event_request: ReloadEventRequest,
    db_session: Session,
    today: date,
) -> None:
    """It keeps its place in the newest-first list (ADR-0024 decision 16)."""
    draft = save_draft(ORGANISER_ID, COMPLETE_DRAFT_PAYLOAD)
    draft.created_at = FIRST_SAVED_AT
    db_session.commit()

    _submit(DRAFT_REFERENCE, db_session, today)

    created_at = reload_event_request(draft.id).created_at
    # SQLite stores no time zone, so the value comes back without one.
    assert created_at.replace(tzinfo=timezone.utc) == FIRST_SAVED_AT


def test_a_submitted_drafts_end_date_defaults_to_its_proposed_date(
    saved_users: list[User],
    save_draft: SaveDraft,
    reload_event_request: ReloadEventRequest,
    db_session: Session,
    today: date,
) -> None:
    draft = save_draft(ORGANISER_ID, COMPLETE_DRAFT_PAYLOAD)

    _submit(DRAFT_REFERENCE, db_session, today)

    assert reload_event_request(draft.id).end_date == date(2026, 10, 15)


def test_a_submitted_draft_goes_to_the_least_loaded_coordinator_with_history_and_a_notification(
    saved_users: list[User],
    save_draft: SaveDraft,
    coordinator_of: Callable[[int], int | None],
    history_of: Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]],
    notifications_of: Callable[[int], list[tuple[Any, ...]]],
    db_session: Session,
    today: date,
) -> None:
    draft = save_draft(ORGANISER_ID, COMPLETE_DRAFT_PAYLOAD)

    _submit(DRAFT_REFERENCE, db_session, today)

    assert coordinator_of(draft.id) == 3
    assert history_of(draft.id) == [
        (EventHistoryKind.COORDINATOR_ASSIGNED, None, {"coordinator_id": 3})
    ]
    assert len(notifications_of(3)) == 1


def test_colleagues_see_the_request_once_it_is_submitted(
    other_organisers: list[User], save_draft: SaveDraft, db_session: Session, today: date
) -> None:
    save_draft(ORGANISER_ID, COMPLETE_DRAFT_PAYLOAD)

    _submit(DRAFT_REFERENCE, db_session, today)

    colleagues_list = list_event_requests_for_organiser(COLLEAGUE_ID)
    assert DRAFT_REFERENCE in {event_request.reference for event_request in colleagues_list}


# --------------------------------------------------------------------------
# Submission fails exactly as a fresh POST /requests would, and saves nothing
# --------------------------------------------------------------------------


@pytest.mark.parametrize("missing_field", INCOMPLETE_DETAIL_FIELDS)
def test_an_incomplete_draft_cannot_be_submitted(
    saved_users: list[User],
    save_draft: SaveDraft,
    reload_event_request: ReloadEventRequest,
    coordinator_of: Callable[[int], int | None],
    history_of: Callable[[int], list[tuple[Any, ...]]],
    notifications_of: Callable[[int], list[tuple[Any, ...]]],
    db_session: Session,
    today: date,
    missing_field: str,
) -> None:
    payload = {key: value for key, value in COMPLETE_DRAFT_PAYLOAD.items() if key != missing_field}
    draft = save_draft(ORGANISER_ID, payload)

    with pytest.raises(ValidationError) as exc_info:
        _submit(DRAFT_REFERENCE, db_session, today)

    assert exc_info.value.status_code == 400
    errors = exc_info.value.details or {}
    assert "Missing data for required field." in errors[missing_field]
    assert reload_event_request(draft.id).status is EventRequestStatus.DRAFT
    assert coordinator_of(draft.id) is None
    assert history_of(draft.id) == []
    assert notifications_of(3) == []


@pytest.mark.parametrize(("extra_fields", "field", "message"), RULE_BREAKING_CASES)
def test_submitting_applies_every_submission_rule(
    saved_users: list[User],
    save_draft: SaveDraft,
    reload_event_request: ReloadEventRequest,
    db_session: Session,
    today: date,
    extra_fields: dict[str, str],
    field: str,
    message: str,
) -> None:
    payload = {**COMPLETE_DRAFT_PAYLOAD, **extra_fields}
    draft = save_draft(ORGANISER_ID, payload)

    with pytest.raises(ValidationError) as exc_info:
        _submit(DRAFT_REFERENCE, db_session, today)

    errors = exc_info.value.details or {}
    assert message in errors[field]
    assert reload_event_request(draft.id).status is EventRequestStatus.DRAFT


def test_only_a_draft_can_be_submitted(
    saved_users: list[User], save_draft: SaveDraft, db_session: Session, today: date
) -> None:
    save_draft(ORGANISER_ID, COMPLETE_DRAFT_PAYLOAD)
    _submit(DRAFT_REFERENCE, db_session, today)

    with pytest.raises(RequestNotDraftError) as exc_info:
        _submit(DRAFT_REFERENCE, db_session, today)

    assert (exc_info.value.status_code, exc_info.value.error_code) == (409, "request_not_draft")
    assert exc_info.value.message == NOT_A_DRAFT_MESSAGE


def test_a_colleagues_draft_cannot_be_submitted(
    other_organisers: list[User], save_draft: SaveDraft, db_session: Session, today: date
) -> None:
    save_draft(COLLEAGUE_ID, COMPLETE_DRAFT_PAYLOAD)

    with pytest.raises(NotFoundError) as exc_info:
        _submit(DRAFT_REFERENCE, db_session, today)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
