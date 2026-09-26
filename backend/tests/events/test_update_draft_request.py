"""Unit tests for SCRUM-20 "Save and resume a draft event request" — editing a draft.

AC3: an Organiser can reopen a draft, change any of its fields, and save it again.
A ``PATCH`` is partial: only the fields sent change, a field sent as ``null`` clears
it, and an empty body changes nothing (ADR-0024) — except ``name``, which still
identifies the draft to its author and so can never be blank or null. A request
past the draft stage is refused with ``409 request_not_draft``; a colleague's draft
gets the same ``404`` as an unknown reference, so it can't be probed (ADR-0012).

Runs against ``db_session`` with ``saved_users``: organiser 7, in client
organisation 3.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, time
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import (
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    NOT_A_DRAFT_MESSAGE,
    RequestNotDraftError,
    get_event_request_for_organiser,
    update_draft_event_request,
)
from tests.events.cases import DRAFT_REFERENCE, FIELD_REJECTED_CASES, NON_DRAFT_STATUSES

pytestmark = pytest.mark.scrum_20

ORGANISER_ID = 7
COLLEAGUE_ID = 8
SaveDraft = Callable[[int, dict[str, Any]], EventRequest]
ReloadEventRequest = Callable[[int], EventRequest]


def _update(reference: str, payload: dict[str, Any], session: Session) -> EventRequest:
    """Update ``reference`` as organiser 7 on ``session``."""
    return update_draft_event_request(ORGANISER_ID, reference, payload, session=session)


def _refused_edit(payload: dict[str, Any], session: Session) -> dict[str, list[str]]:
    """Edit the draft with ``payload``, expecting a 400; return the error's details."""
    with pytest.raises(ValidationError) as exc_info:
        _update(DRAFT_REFERENCE, payload, session)

    assert exc_info.value.status_code == 400
    return exc_info.value.details or {}


# --------------------------------------------------------------------------
# AC3 — reopen a draft, change any of its fields, and save it again
# --------------------------------------------------------------------------


def test_a_saved_draft_can_be_reopened(saved_users: list[User], save_draft: SaveDraft) -> None:
    save_draft(ORGANISER_ID, {"name": "Just an idea"})

    reopened = get_event_request_for_organiser(ORGANISER_ID, DRAFT_REFERENCE)

    assert reopened.status is EventRequestStatus.DRAFT
    assert reopened.name == "Just an idea"


def test_any_field_of_a_draft_can_be_changed_and_saved_again(
    saved_users: list[User],
    save_draft: SaveDraft,
    reload_event_request: ReloadEventRequest,
    db_session: Session,
) -> None:
    draft = save_draft(ORGANISER_ID, {"name": "Just an idea"})
    payload = {
        "name": "Partner Summit",
        "purpose": "Annual showcase",
        "description": "Full day event",
        "proposed_date": "2026-10-15",
        "end_date": "2026-10-16",
        "start_time": "09:00",
        "end_time": "17:00",
        "expected_attendance": 250,
        "venue_requirements": "Main hall",
        "accessibility_needs": "Step-free access",
        "equipment_requirements": "Projector",
        "registration_required": True,
    }

    updated = _update(DRAFT_REFERENCE, payload, db_session)

    assert updated.id == draft.id
    reloaded = reload_event_request(draft.id)
    assert reloaded.name == "Partner Summit"
    assert reloaded.purpose == "Annual showcase"
    assert reloaded.description == "Full day event"
    assert reloaded.proposed_date == date(2026, 10, 15)
    assert reloaded.end_date == date(2026, 10, 16)
    assert reloaded.start_time == time(9, 0)
    assert reloaded.end_time == time(17, 0)
    assert reloaded.expected_attendance == 250
    assert reloaded.venue_requirements == "Main hall"
    assert reloaded.accessibility_needs == "Step-free access"
    assert reloaded.equipment_requirements == "Projector"
    assert reloaded.registration_required is True
    assert reloaded.status is EventRequestStatus.DRAFT


def test_only_the_fields_sent_change(
    saved_users: list[User],
    save_draft: SaveDraft,
    reload_event_request: ReloadEventRequest,
    db_session: Session,
) -> None:
    draft = save_draft(
        ORGANISER_ID,
        {"name": "Partner Summit", "purpose": "Old purpose", "proposed_date": "2026-10-15"},
    )

    _update(DRAFT_REFERENCE, {"purpose": "New purpose"}, db_session)

    reloaded = reload_event_request(draft.id)
    assert reloaded.purpose == "New purpose"
    assert reloaded.name == "Partner Summit"
    assert reloaded.proposed_date == date(2026, 10, 15)


def test_a_field_sent_as_null_is_cleared(
    saved_users: list[User],
    save_draft: SaveDraft,
    reload_event_request: ReloadEventRequest,
    db_session: Session,
) -> None:
    draft = save_draft(ORGANISER_ID, {"name": "Just an idea", "purpose": "Something"})

    _update(DRAFT_REFERENCE, {"purpose": None}, db_session)

    assert reload_event_request(draft.id).purpose is None


@pytest.mark.parametrize("name", [None, "   "], ids=["null", "blank"])
def test_the_name_cannot_be_cleared(
    saved_users: list[User],
    save_draft: SaveDraft,
    reload_event_request: ReloadEventRequest,
    db_session: Session,
    name: str | None,
) -> None:
    draft = save_draft(ORGANISER_ID, {"name": "Just an idea"})

    errors = _refused_edit({"name": name}, db_session)

    assert "name" in errors
    assert reload_event_request(draft.id).name == "Just an idea"


@pytest.mark.parametrize(("field", "value"), FIELD_REJECTED_CASES)
def test_the_fields_sent_are_checked(
    saved_users: list[User],
    save_draft: SaveDraft,
    reload_event_request: ReloadEventRequest,
    db_session: Session,
    field: str,
    value: Any,
) -> None:
    draft = save_draft(ORGANISER_ID, {"name": "Just an idea"})
    stored_before = getattr(reload_event_request(draft.id), field)

    errors = _refused_edit({field: value}, db_session)

    assert field in errors
    assert getattr(reload_event_request(draft.id), field) == stored_before


def test_an_empty_body_changes_nothing(
    saved_users: list[User],
    save_draft: SaveDraft,
    reload_event_request: ReloadEventRequest,
    db_session: Session,
) -> None:
    draft = save_draft(ORGANISER_ID, {"name": "Just an idea", "purpose": "Something"})

    updated = _update(DRAFT_REFERENCE, {}, db_session)

    assert updated.id == draft.id
    reloaded = reload_event_request(draft.id)
    assert reloaded.name == "Just an idea"
    assert reloaded.purpose == "Something"


@pytest.mark.parametrize("typed", ["evr-dddddddd", " EVR-DDDDDDDD ", "Evr-Dddddddd"])
def test_the_reference_ignores_case_and_surrounding_spaces(
    saved_users: list[User], save_draft: SaveDraft, db_session: Session, typed: str
) -> None:
    draft = save_draft(ORGANISER_ID, {"name": "Just an idea"})

    updated = _update(typed, {"purpose": "Something"}, db_session)

    assert updated.id == draft.id


# --------------------------------------------------------------------------
# Refused edits change nothing
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", NON_DRAFT_STATUSES, ids=lambda status: status.value)
def test_a_request_past_the_draft_stage_cannot_be_changed_as_a_draft(
    saved_users: list[User],
    save_draft: SaveDraft,
    reload_event_request: ReloadEventRequest,
    db_session: Session,
    status: EventRequestStatus,
) -> None:
    # Full details, so moving off draft does not itself break the check constraint
    # that requires them once a request is no longer a draft (ADR-0024).
    draft = save_draft(
        ORGANISER_ID,
        {
            "name": "Just an idea",
            "proposed_date": "2026-10-15",
            "start_time": "09:00",
            "end_time": "17:00",
            "expected_attendance": 250,
        },
    )
    # Read proposed_date before changing anything: the session expires attributes
    # on commit, and reading it after status changes would autoflush that change
    # alone, tripping the very constraint this setup is working around.
    proposed_date = draft.proposed_date
    draft.status = status
    draft.end_date = proposed_date
    db_session.commit()

    with pytest.raises(RequestNotDraftError) as exc_info:
        _update(DRAFT_REFERENCE, {"purpose": "Something"}, db_session)

    assert (exc_info.value.status_code, exc_info.value.error_code) == (409, "request_not_draft")
    assert exc_info.value.message == NOT_A_DRAFT_MESSAGE
    assert reload_event_request(draft.id).purpose is None


def test_a_colleagues_draft_cannot_be_changed(
    other_organisers: list[User], save_draft: SaveDraft, db_session: Session
) -> None:
    save_draft(COLLEAGUE_ID, {"name": "Colleague's idea"})

    with pytest.raises(NotFoundError) as exc_info:
        _update(DRAFT_REFERENCE, {"purpose": "Something"}, db_session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE


def test_an_unknown_reference_is_not_found(saved_users: list[User], db_session: Session) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        _update("EVR-ZZZZZZZZ", {"purpose": "Something"}, db_session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE


def test_changing_a_draft_notifies_nobody(
    saved_users: list[User],
    save_draft: SaveDraft,
    db_session: Session,
    notifications_of: Callable[[int], list[tuple[Any, ...]]],
) -> None:
    save_draft(ORGANISER_ID, {"name": "Just an idea"})

    _update(DRAFT_REFERENCE, {"purpose": "Something"}, db_session)

    assert notifications_of(3) == []
    assert notifications_of(9) == []
