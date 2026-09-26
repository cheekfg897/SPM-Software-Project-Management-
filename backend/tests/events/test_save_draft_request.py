"""Unit tests for SCRUM-20 "Save and resume a draft event request" — saving a draft.

AC1: an Organiser can save a request with only the event name. AC2: a saved draft
shows status ``draft`` (the client draws the rest of AC2 from that and from its
``null`` details). AC4 (saving half): a draft is filed under its author's client
organisation like any other request, but gets no coordinator, no history entry and
no notification, since nothing has happened to it but being saved (ADR-0024). Field
rules beyond "name is required" are the same ones SCRUM-19 already checks, applied
to whichever fields a draft happens to include; the rules that only make sense once
a request is submitted (ADR-0001, ADR-0002) do not apply here.

Runs against ``db_session`` with ``saved_users``: organiser 7, in client organisation
3. The reference collision test uses ``mock_session``, matching SCRUM-19's own.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, time
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.schemas import NAME_MAX_LENGTH, EventRequestSchema
from app.modules.events.services import (
    REFERENCE_UNIQUE_CONSTRAINT,
    OrganiserWithoutOrganisationError,
    list_event_requests_for_organiser,
    save_draft_event_request,
)
from tests.events.cases import DETAIL_COLUMNS, DRAFT_REFERENCE, DriverError

pytestmark = pytest.mark.scrum_20

ORGANISER_ID = 7
SaveDraft = Callable[[int, dict[str, Any]], EventRequest]
ReloadEventRequest = Callable[[int], EventRequest]

#: Payloads whose ``name`` a draft must refuse (AC1 only requires a *valid* name).
NAME_REJECTED_PAYLOADS = [
    pytest.param({"purpose": "Annual showcase"}, id="missing"),
    pytest.param({"name": "   "}, id="blank"),
    pytest.param({"name": None}, id="null"),
    pytest.param({"name": "x" * (NAME_MAX_LENGTH + 1)}, id="too_long"),
]

#: One field at a time, each with a value its own rule refuses.
FIELD_REJECTED_CASES = [
    ("proposed_date", "soon"),
    ("start_time", "25:00"),
    ("start_time", "09:00+08:00"),
    ("expected_attendance", 0),
    ("expected_attendance", "50"),
    ("expected_attendance", True),
    ("registration_required", "yes"),
]


def _saved_references(session: Session) -> set[str]:
    """Every reference saved so far, to check a rejected save wrote nothing."""
    return set(session.scalars(select(EventRequest.reference)))


def _save_rejected(session: Session, payload: dict[str, Any]) -> dict[str, list[str]]:
    """Try to save ``payload``; check it is refused as invalid and saves nothing."""
    with pytest.raises(ValidationError) as exc_info:
        save_draft_event_request(ORGANISER_ID, payload, session=session)

    assert exc_info.value.status_code == 400
    assert _saved_references(session) == set()
    return exc_info.value.details or {}


# --------------------------------------------------------------------------
# AC1 — a draft can be saved with only its name
# --------------------------------------------------------------------------


def test_a_draft_can_be_saved_with_only_its_name(
    saved_users: list[User], save_draft: SaveDraft, reload_event_request: ReloadEventRequest
) -> None:
    draft = save_draft(ORGANISER_ID, {"name": "Just an idea"})

    reloaded = reload_event_request(draft.id)
    assert reloaded.status is EventRequestStatus.DRAFT
    assert reloaded.reference == DRAFT_REFERENCE
    assert reloaded.organiser_id == ORGANISER_ID
    assert reloaded.organisation_id == 3
    assert reloaded.name == "Just an idea"
    assert reloaded.registration_required is False
    for column in DETAIL_COLUMNS:
        assert getattr(reloaded, column) is None


def test_a_draft_keeps_every_field_supplied(
    saved_users: list[User], save_draft: SaveDraft, reload_event_request: ReloadEventRequest
) -> None:
    payload = {
        "name": "Partner Summit",
        "purpose": "Annual showcase",
        "proposed_date": "2026-10-15",
        "start_time": "09:00",
        "end_time": "17:00",
        "expected_attendance": 250,
        "registration_required": True,
    }

    draft = save_draft(ORGANISER_ID, payload)

    reloaded = reload_event_request(draft.id)
    assert reloaded.purpose == "Annual showcase"
    assert reloaded.proposed_date == date(2026, 10, 15)
    assert reloaded.start_time == time(9, 0)
    assert reloaded.end_time == time(17, 0)
    assert reloaded.expected_attendance == 250
    assert reloaded.registration_required is True
    # end_date defaults only on submission (ADR-0024 20-8), so left out it stays None.
    assert reloaded.end_date is None


@pytest.mark.parametrize("payload", NAME_REJECTED_PAYLOADS)
def test_a_draft_needs_a_name(
    db_session: Session, saved_users: list[User], payload: dict[str, Any]
) -> None:
    errors = _save_rejected(db_session, payload)

    assert "name" in errors


@pytest.mark.parametrize(("field", "value"), FIELD_REJECTED_CASES)
def test_each_field_supplied_is_checked(
    db_session: Session, saved_users: list[User], field: str, value: Any
) -> None:
    payload = {"name": "Just an idea", field: value}

    errors = _save_rejected(db_session, payload)

    assert field in errors


def test_a_draft_may_hold_details_submission_would_refuse(
    saved_users: list[User], save_draft: SaveDraft, reload_event_request: ReloadEventRequest
) -> None:
    payload = {
        "name": "Past idea",
        "proposed_date": "2020-01-01",  # long in the past
        "start_time": "14:00",
        "end_time": "13:00",  # ends before it starts
    }

    draft = save_draft(ORGANISER_ID, payload)

    reloaded = reload_event_request(draft.id)
    assert reloaded.proposed_date == date(2020, 1, 1)
    assert reloaded.start_time == time(14, 0)
    assert reloaded.end_time == time(13, 0)


@pytest.mark.parametrize("field", ["status", "reference", "organiser_id"])
def test_server_controlled_fields_cannot_be_set(
    db_session: Session, saved_users: list[User], field: str
) -> None:
    payload = {"name": "Just an idea", field: "anything"}

    errors = _save_rejected(db_session, payload)

    assert field in errors


# --------------------------------------------------------------------------
# AC4 — a draft belongs to its author's organisation; nothing else happens to it
# --------------------------------------------------------------------------


def test_an_organiser_without_an_organisation_cannot_save_a_draft(
    other_organisers: list[User], db_session: Session
) -> None:
    unlinked_organiser_id = 10

    payload = {"name": "Just an idea"}
    with pytest.raises(OrganiserWithoutOrganisationError) as exc_info:
        save_draft_event_request(unlinked_organiser_id, payload, session=db_session)

    assert exc_info.value.status_code == 403


def test_saving_a_draft_assigns_no_coordinator_records_no_history_and_notifies_nobody(
    saved_users: list[User],
    save_draft: SaveDraft,
    coordinator_of: Callable[[int], int | None],
    history_of: Callable[[int], list[tuple[Any, ...]]],
    notifications_of: Callable[[int], list[tuple[Any, ...]]],
) -> None:
    draft = save_draft(ORGANISER_ID, {"name": "Just an idea"})

    assert coordinator_of(draft.id) is None
    assert history_of(draft.id) == []
    assert notifications_of(3) == []  # the coordinator submitting would have picked


def test_a_draft_reference_collision_is_retried(
    mock_session: MagicMock,
    organiser_is_found: None,
    integrity_error: Callable[[Exception], IntegrityError],
    references_in_order: Callable[..., Callable[[], str]],
) -> None:
    collision = integrity_error(DriverError(REFERENCE_UNIQUE_CONSTRAINT))
    mock_session.commit.side_effect = [collision, None]

    draft = save_draft_event_request(
        "7",
        {"name": "Just an idea"},
        session=mock_session,
        reference_factory=references_in_order("EVR-AAAAAAAA", "EVR-BBBBBBBB"),
    )

    assert draft.reference == "EVR-BBBBBBBB"
    assert mock_session.add.call_count == 2
    mock_session.rollback.assert_called_once()


# --------------------------------------------------------------------------
# AC2 — the list shows the draft as draft, beside submitted requests
# --------------------------------------------------------------------------


def test_the_organisers_list_shows_the_draft_as_draft_beside_submitted_requests(
    saved_users: list[User],
    save_draft: SaveDraft,
    submit_valid_request: Callable[..., EventRequest],
) -> None:
    save_draft(ORGANISER_ID, {"name": "Just an idea"})
    submit_valid_request()

    listed = list_event_requests_for_organiser(ORGANISER_ID)
    dumped = EventRequestSchema(many=True).dump(listed)

    statuses = {row["status"] for row in dumped}
    assert statuses == {"draft", "submitted"}
    draft_row = next(row for row in dumped if row["status"] == "draft")
    for column in DETAIL_COLUMNS:
        assert draft_row[column] is None
