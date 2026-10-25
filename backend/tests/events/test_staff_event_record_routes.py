"""Route tests for the read-only event record internal users open (SCRUM-24 AC9, AC10).

``GET /api/events/requests/<reference>/staff-record`` (ADR-0095) opens to Venue Staff,
Technical Support Staff, the Safety Officer (AC9) and the Event Coordinator Lead
(AC10), and to no one else. An Event Coordinator keeps their own record route, which
opens only the events assigned to them (AC10, ADR-0034), so they are refused here
whatever the event. The organiser and the attendee are refused too. The record shows
SCRUM-84 AC2's and SCRUM-85 AC2's preparation details and no registrants (SCRUM-55).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.equipment.models import PreparationStatus
from app.modules.equipment.services import ReservationAsShown
from app.modules.events import routes
from app.modules.events.models import EquipmentLineStatus, EventRequest
from app.modules.events.services import (
    ClarificationAsShown,
    CoordinatorContact,
    DecisionAsShown,
    EventRecord,
    SafetyOutcomeAsShown,
    SafetyReviewEquipment,
    StaffEventRecord,
)
from app.modules.venue.models import (
    PreparationStatus as VenuePreparationStatus,
)
from tests.events.cases import arrangement_for_record

pytestmark = pytest.mark.scrum_24

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
TokenFor = Callable[..., str]

ENDPOINT = "events.get_staff_record"
REFERENCE = "EVR-AAAAAAAA"
PATH = f"/api/events/requests/{REFERENCE}/staff-record"
SERVICE = "get_staff_event_record"

#: The roles AC9 and AC10 let open any submitted event's read-only record.
READER_ROLES = [
    Role.EVENT_COORDINATOR_LEAD,
    Role.SAFETY_OFFICER,
    Role.TECHNICAL_SUPPORT_STAFF,
    Role.VENUE_STAFF,
]
#: Everyone else, written out so a role added later must be placed on purpose.
REFUSED_ROLES = [Role.ATTENDEE, Role.EVENT_COORDINATOR, Role.EVENT_ORGANISER]

CHECKED_AT = datetime(2026, 10, 2, 2, 0, tzinfo=timezone.utc)
CHECKLIST = {"attendance_vs_capacity": "250 expected; the hall holds 300."}


@pytest.fixture()
def staff_record(
    make_event_request: Callable[..., EventRequest], coordinator_three: CoordinatorContact
) -> StaffEventRecord:
    """A record with one of everything it shows, as the service would return it."""
    event_request = make_event_request(coordinator_id=3)
    event_request.programme_notes = "Doors open at 08:30."
    event_request.internal_planning_notes = "Client is sensitive about the date."
    record = EventRecord(
        event_request=event_request,
        coordinator=coordinator_three,
        decision=DecisionAsShown(
            outcome="approved", reason=None, decided_by="Coordinator Three", decided_at=CHECKED_AT
        ),
        clarifications=(
            ClarificationAsShown(
                message="How many guests use wheelchairs?",
                requested_by="Coordinator Three",
                requested_at=CHECKED_AT,
            ),
        ),
    )
    return StaffEventRecord(
        record=record,
        venue_arrangements=[
            arrangement_for_record(
                starts_at=datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc),
                ends_at=datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc),
                preparation_status=VenuePreparationStatus.IN_PROGRESS,
                preparation_notes="Chairs set out.",
            )
        ],
        equipment_lines=[
            SafetyReviewEquipment(
                equipment_type_name="Projector",
                quantity=2,
                notes="Needs HDMI",
                status=EquipmentLineStatus.PARTIALLY_FULFILLED,
                provided_quantity=1,
                outcome_note="Only one is free that day.",
            )
        ],
        equipment_reservations=[
            ReservationAsShown(
                id=12,
                equipment_type_id=4,
                equipment_type_name="Projector",
                quantity=1,
                starts_at=datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc),
                ends_at=datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc),
                reserved_by="Tess Tech",
                created_at=CHECKED_AT,
                needs_attention=False,
                preparation_status=PreparationStatus.READY,
                preparation_notes="Tested.",
            )
        ],
        safety_outcome=SafetyOutcomeAsShown(
            outcome="approved",
            checklist=CHECKLIST,
            reason=None,
            recorded_by="Sam Safety",
            recorded_at=CHECKED_AT,
        ),
    )


def _open(call_route: CallRoute, token: str | None) -> tuple[Any, int]:
    return call_route(ENDPOINT, "GET", PATH, {"reference": REFERENCE}, token)


# --------------------------------------------------------------------------
# AC9, AC10 — who may open it
# --------------------------------------------------------------------------


def test_the_readers_and_the_refused_roles_are_every_role() -> None:
    assert set(READER_ROLES) | set(REFUSED_ROLES) == ALL_ROLES
    assert set(READER_ROLES).isdisjoint(REFUSED_ROLES)


def test_the_record_opens_to_the_internal_reviewers_and_the_lead_only(app: Flask) -> None:
    allowed_roles = app.view_functions[ENDPOINT].allowed_roles  # type: ignore[attr-defined]

    assert allowed_roles == frozenset(role.value for role in READER_ROLES)


@pytest.mark.parametrize("role", READER_ROLES, ids=lambda role: role.value)
def test_each_reader_opens_the_record_by_its_reference(
    call_route: CallRoute,
    replace_services: ReplaceServices,
    token_for: TokenFor,
    staff_record: StaffEventRecord,
    role: Role,
) -> None:
    mocks = replace_services(routes, {SERVICE: staff_record})

    response, status = _open(call_route, token_for(role=role))

    assert status == 200
    assert response.get_json()["reference"] == REFERENCE
    mocks[SERVICE].assert_called_once_with(REFERENCE)


@pytest.mark.parametrize("role", REFUSED_ROLES, ids=lambda role: role.value)
def test_every_other_role_is_refused_and_the_record_is_not_read(
    call_route: CallRoute, replace_services: ReplaceServices, token_for: TokenFor, role: Role
) -> None:
    """An Event Coordinator too, assigned or not: their record is their own route."""
    mocks = replace_services(routes, {SERVICE: None})

    with pytest.raises(AuthorizationError) as exc_info:
        _open(call_route, token_for(role=role))

    assert exc_info.value.status_code == 403
    mocks[SERVICE].assert_not_called()


def test_opening_the_record_without_a_token_is_401(
    call_route: CallRoute, replace_services: ReplaceServices
) -> None:
    mocks = replace_services(routes, {SERVICE: None})

    with pytest.raises(AuthenticationError) as exc_info:
        _open(call_route, None)

    assert exc_info.value.status_code == 401
    mocks[SERVICE].assert_not_called()


# --------------------------------------------------------------------------
# AC9, SCRUM-84 AC2, SCRUM-85 AC2 — what the record shows
# --------------------------------------------------------------------------


def test_the_record_shows_every_section_and_no_ids_or_registrants(
    call_route: CallRoute,
    replace_services: ReplaceServices,
    token_for: TokenFor,
    staff_record: StaffEventRecord,
) -> None:
    replace_services(routes, {SERVICE: staff_record})

    response, _ = _open(call_route, token_for(role=Role.VENUE_STAFF))

    assert response.get_json() == {
        "reference": REFERENCE,
        "status": "submitted",
        "name": "Partner Summit",
        "purpose": None,
        "description": None,
        "proposed_date": "2026-10-15",
        "end_date": "2026-10-15",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "expected_attendance": 250,
        "venue_requirements": None,
        "accessibility_needs": None,
        "equipment_requirements": None,
        "registration_required": False,
        "created_at": None,
        "programme_notes": "Doors open at 08:30.",
        "internal_planning_notes": "Client is sensitive about the date.",
        "coordinator": {"full_name": "Coordinator Three", "email": "coordinator3@example.com"},
        "decision": {
            "outcome": "approved",
            "reason": None,
            "decided_by": "Coordinator Three",
            "decided_at": "2026-10-02T10:00:00+08:00",
        },
        "clarifications": [
            {
                "message": "How many guests use wheelchairs?",
                "requested_by": "Coordinator Three",
                "requested_at": "2026-10-02T10:00:00+08:00",
                "response": None,
                "answered_by": None,
                "answered_at": None,
            }
        ],
        "venue_arrangements": [
            {
                "venue_name": "Main Hall",
                "starts_at": "2026-11-01T09:00:00+08:00",
                "ends_at": "2026-11-01T17:00:00+08:00",
                "status": "approved",
                "preparation_status": "in_progress",
                "preparation_notes": "Chairs set out.",
            }
        ],
        "equipment_lines": [
            {
                "equipment_type_name": "Projector",
                "quantity": 2,
                "notes": "Needs HDMI",
                "status": "partially_fulfilled",
                "provided_quantity": 1,
                "outcome_note": "Only one is free that day.",
            }
        ],
        "equipment_reservations": [
            {
                "equipment_type_name": "Projector",
                "quantity": 1,
                "starts_at": "2026-11-01T09:00:00+08:00",
                "ends_at": "2026-11-01T17:00:00+08:00",
                "reserved_by": "Tess Tech",
                "preparation_status": "ready",
                "preparation_notes": "Tested.",
            }
        ],
        "safety_outcome": {
            "outcome": "approved",
            "checklist": CHECKLIST,
            "reason": None,
            "recorded_by": "Sam Safety",
            "recorded_at": "2026-10-02T10:00:00+08:00",
        },
    }


def test_a_record_with_no_coordinator_decision_or_safety_outcome_shows_them_as_null(
    call_route: CallRoute,
    replace_services: ReplaceServices,
    token_for: TokenFor,
    make_event_request: Callable[..., EventRequest],
) -> None:
    """What the Lead sees of an event still in their queue (AC10)."""
    unassigned = StaffEventRecord(
        record=EventRecord(event_request=make_event_request(), coordinator=None),
        venue_arrangements=[],
        equipment_lines=[],
        equipment_reservations=[],
        safety_outcome=None,
    )
    replace_services(routes, {SERVICE: unassigned})

    response, _ = _open(call_route, token_for(role=Role.EVENT_COORDINATOR_LEAD))

    body = response.get_json()
    sections = {}
    for name in ("coordinator", "decision", "safety_outcome", "clarifications"):
        sections[name] = body[name]
    assert sections == {
        "coordinator": None,
        "decision": None,
        "safety_outcome": None,
        "clarifications": [],
    }
