"""SCRUM-97: an approved event is settled and sent to the Safety Officer, via the API.

An approved event has a venue booked and an equipment line. The coordinator can't send
it to Safety Review while the venue is pending (AC1). Venue Staff approve the booking,
Technical Support record the equipment outcome, and the coordinator sends the event. It
is then in the Safety Officer's awaiting list with its venue and equipment (AC5, AC6),
and the Safety Officer has the notification (AC4). SCRUM-98: the Safety Officer
requests changes, which sends the event back to planning; the coordinator sends it
again and the Safety Officer approves it, which takes it off their list. SCRUM-49: the
coordinator can't confirm the event before that approval; once it is in, they confirm
it and the event is confirmed. Every call goes through the real routes with Flask's test
client (ADR-0031).

Nothing here walks the request to approval: the event is saved as approved, with its
coordinator, and that journey is test_request_to_approval_journey.py.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session
from werkzeug.test import TestResponse

from app.common.clock import local_today
from app.modules.auth.permissions import Role
from app.modules.auth.services import create_staff_user
from app.modules.events.models import EventRequest, EventRequestStatus
from tests.e2e.actors import Actor, SignIn

pytestmark = [pytest.mark.scrum_97, pytest.mark.scrum_98, pytest.mark.scrum_49, pytest.mark.e2e]

PASSWORD = "Password123"
COORDINATOR_ACCOUNT = {"full_name": "Cara Coordinator", "email": "cara@example.com"}
VENUE_STAFF_ACCOUNT = {"full_name": "Vera Venue", "email": "vera@example.com"}
TECHNICAL_SUPPORT_ACCOUNT = {"full_name": "Tina Technician", "email": "tina@example.com"}
SAFETY_OFFICER_ACCOUNT = {"full_name": "Sam Safety", "email": "sam@example.com"}
EVENT = "EVR-AAAAAAAA"
VENUE = {
    "name": "Main Hall",
    "location": "Level 1",
    "capacity": 300,
    "supported_layouts": ["theatre"],
    "facilities": ["projector"],
    "accessibility_features": ["wheelchair_access"],
}
PROJECTORS = {"name": "Projector", "total_quantity": 10, "store_name": "Central AV store"}
#: The Safety Officer's note on each of SCRUM-98 AC2's seven items.
CHECKLIST = {
    "attendance_vs_capacity": "80 expected in a hall for 300.",
    "venue_layout": "Theatre layout, aisles clear.",
    "emergency_access": "Two exits, both signed.",
    "accessibility": "Step-free entrance confirmed.",
    "equipment_placement": "Projector cables taped down.",
    "crowd_movement": "One-way flow at the doors.",
    "venue_restrictions": "No open flames.",
}


def _body(response: TestResponse, expected_status: int) -> Any:
    """The response's JSON, once its status is the one expected."""
    body = response.get_json()
    assert response.status_code == expected_status, body
    return body


def _latest_notification_kind(actor: Actor) -> str | None:
    """The kind of the actor's newest notification, or ``None`` if they have none."""
    notifications = _body(actor.get("/api/notifications"), 200)["notifications"]
    return notifications[0]["kind"] if notifications else None


def _create_staff(account: dict[str, str], role: Role, session: Session) -> int:
    """Create a staff account as staff are created (ADR-0023); return its user id."""
    user = create_staff_user({**account, "password": PASSWORD, "role": role.value}, session=session)
    return user.id


def _staff_actor(account: dict[str, str], role: Role, session: Session, sign_in: SignIn) -> Actor:
    """Create a staff account and sign it in."""
    _create_staff(account, role, session)
    return sign_in(account["email"], PASSWORD)


@pytest.fixture()
def coordinator_id(db_session: Session) -> int:
    """The Event Coordinator's user id; the event is assigned to them."""
    return _create_staff(COORDINATOR_ACCOUNT, Role.EVENT_COORDINATOR, db_session)


@pytest.fixture()
def coordinator(coordinator_id: int, sign_in: SignIn) -> Actor:
    """The Event Coordinator, signed in."""
    return sign_in(COORDINATOR_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def venue_staff(db_session: Session, sign_in: SignIn) -> Actor:
    """The Venue Staff account, signed in."""
    return _staff_actor(VENUE_STAFF_ACCOUNT, Role.VENUE_STAFF, db_session, sign_in)


@pytest.fixture()
def technical_support(db_session: Session, sign_in: SignIn) -> Actor:
    """The Technical Support account, signed in."""
    return _staff_actor(
        TECHNICAL_SUPPORT_ACCOUNT, Role.TECHNICAL_SUPPORT_STAFF, db_session, sign_in
    )


@pytest.fixture()
def safety_officer(db_session: Session, sign_in: SignIn) -> Actor:
    """The only Safety Officer, signed in."""
    return _staff_actor(SAFETY_OFFICER_ACCOUNT, Role.SAFETY_OFFICER, db_session, sign_in)


@pytest.fixture()
def event_day() -> str:
    """The day of the event, a month away, as an ISO date."""
    return (local_today() + timedelta(days=30)).isoformat()


@pytest.fixture()
def approved_event(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    coordinator_id: int,
    event_day: str,
) -> None:
    """An approved event, assigned to the coordinator."""
    event_request = make_event_request(
        reference=EVENT,
        status=EventRequestStatus.APPROVED,
        coordinator_id=coordinator_id,
        proposed_date=date.fromisoformat(event_day),
    )
    event_request.accessibility_needs = "Step-free entrance"
    db_session.add(event_request)
    db_session.commit()


def test_a_settled_event_reaches_the_safety_officer(
    coordinator: Actor,
    venue_staff: Actor,
    technical_support: Actor,
    safety_officer: Actor,
    approved_event: None,
    event_day: str,
) -> None:
    safety_review_path = f"/api/events/requests/{EVENT}/safety-review"
    awaiting_path = "/api/events/requests/awaiting-safety-review"

    # --- A venue is booked: pending, and the event can't go yet (SCRUM-97 AC1) ---
    venue = _body(venue_staff.post("/api/venues", VENUE), 201)
    booking = {
        "venue_id": venue["id"],
        "starts_at": f"{event_day}T09:00:00+08:00",
        "ends_at": f"{event_day}T12:00:00+08:00",
        "purpose": "Partner summit",
    }
    arrangement = _body(
        coordinator.post(f"/api/venues/events/{EVENT}/booking-requests", booking), 201
    )
    refused = _body(coordinator.post(safety_review_path), 409)
    assert refused["error"] == "safety_review_not_allowed"
    assert _body(safety_officer.get(awaiting_path), 200) == {
        "events": [],
        "message": "No events are waiting for a safety review.",
    }

    # --- Venue Staff approve it (SCRUM-97 AC1) ---
    decision = {"outcome": "approved"}
    decided = _body(
        venue_staff.post(f"/api/venues/booking-requests/{arrangement['id']}/decision", decision),
        200,
    )
    assert decided["status"] == "approved"

    # --- Equipment is asked for, and Technical Support answer (SCRUM-97 AC1) ---
    projectors = _body(technical_support.post("/api/equipment/types", PROJECTORS), 201)
    line_request = {"equipment_type_id": projectors["id"], "quantity": 2, "notes": "Needs HDMI"}
    line = _body(coordinator.post(f"/api/events/requests/{EVENT}/equipment", line_request), 201)
    assert coordinator.post(safety_review_path).status_code == 409
    outcome = {"provided_quantity": 2}
    outcome_path = f"/api/events/requests/{EVENT}/equipment/{line['id']}/outcome"
    _body(technical_support.post(outcome_path, outcome), 200)

    # --- The coordinator sends the event (SCRUM-97 AC1) ---
    sent = _body(coordinator.post(safety_review_path), 200)
    assert sent["status"] == "safety_review"

    # --- The Safety Officer sees it, with its venue and equipment (AC5, AC6) ---
    [awaiting] = _body(safety_officer.get(awaiting_path), 200)["events"]
    assert awaiting["event"]["name"] == "Partner Summit"
    assert awaiting["event"]["accessibility_needs"] == "Step-free entrance"
    [shown_venue] = awaiting["venues"]
    assert (shown_venue["name"], shown_venue["capacity"]) == ("Main Hall", 300)
    [shown_equipment] = awaiting["equipment"]
    assert (shown_equipment["equipment_type_name"], shown_equipment["provided_quantity"]) == (
        "Projector",
        2,
    )

    # --- ...and has the notification (AC4) ---
    assert _latest_notification_kind(safety_officer) == "safety_review_requested"

    # --- The Safety Officer asks for changes: back to planning (SCRUM-98 AC4, AC6) ---
    outcome_path = f"/api/events/requests/{EVENT}/safety-outcome"
    changes = {"outcome": "changes_requested", "checklist": CHECKLIST}
    assert _body(safety_officer.post(outcome_path, changes), 400)["details"].keys() == {"reason"}
    returned = _body(safety_officer.post(outcome_path, {**changes, "reason": "Exit blocked."}), 200)
    assert returned["status"] == "approved"
    assert _latest_notification_kind(coordinator) == "safety_changes_requested"

    # --- The coordinator sends it again; until the Safety Officer approves, it can't be
    # --- confirmed (SCRUM-49 AC8) ---
    confirm_path = f"/api/events/requests/{EVENT}/confirm"
    _body(coordinator.post(safety_review_path), 200)
    unconfirmed = _body(coordinator.post(confirm_path), 409)
    assert unconfirmed["error"] == "confirmation_not_allowed"
    assert unconfirmed["details"].keys() == {"safety_check"}

    # --- The Safety Officer approves (SCRUM-98 AC1, AC5) ---
    approval = {"outcome": "approved", "checklist": CHECKLIST}
    approved = _body(safety_officer.post(outcome_path, approval), 200)
    assert approved["status"] == "safety_review"
    assert _body(safety_officer.get(awaiting_path), 200)["events"] == []
    assert _latest_notification_kind(coordinator) == "safety_check_approved"
    # Approved once is enough: a second outcome is refused.
    assert _body(safety_officer.post(outcome_path, approval), 409)["error"] == (
        "safety_outcome_not_allowed"
    )

    # --- The coordinator confirms the event (SCRUM-49 AC1) ---
    confirmed = _body(coordinator.post(confirm_path), 200)
    assert confirmed["status"] == "confirmed"
    # Confirmed once is enough: it is no longer in Safety Review to confirm again.
    assert _body(coordinator.post(confirm_path), 409)["error"] == "confirmation_not_allowed"
