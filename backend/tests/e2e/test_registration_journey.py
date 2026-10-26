"""SCRUM-53: attendees take and give up the one place at an event, through the API.

The event starts out approved. The coordinator can't open registration yet, because only
a confirmed event can (SCRUM-69 AC4). A venue is booked and approved, the Safety Officer
approves the event, and the coordinator confirms it (SCRUM-49 AC1), so the event reaches
Confirmed through the real routes rather than being saved that way. The coordinator then
opens registration with room for one. Attendee A registers and sees it in their list.
Attendee B is turned away because the event is full (SCRUM-54 AC2). When A withdraws,
the place is free and B takes it, and A, registering again, finds it gone (SCRUM-53 AC2,
ADR-0032). Every call goes through the real routes with Flask's test client (ADR-0031).

The event is saved as approved with its coordinator; the request-to-approval journey is
test_request_to_approval_journey.py.

The Event Organiser's list of registrants is SCRUM-55's route, which is not on main
yet; add it here when it lands (the organiser sees A withdrawn and B registered).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session
from werkzeug.test import TestResponse

from app.common.clock import local_today
from app.modules.auth.permissions import Role
from app.modules.auth.services import create_staff_user
from app.modules.events.models import EventRequest, EventRequestStatus
from tests.e2e.actors import Actor, SignIn

pytestmark = [pytest.mark.scrum_53, pytest.mark.e2e]

PASSWORD = "Password123"
COORDINATOR_ACCOUNT = {"full_name": "Cara Coordinator", "email": "cara@example.com"}
VENUE_STAFF_ACCOUNT = {"full_name": "Vera Venue", "email": "vera@example.com"}
SAFETY_OFFICER_ACCOUNT = {"full_name": "Sam Safety", "email": "sam@example.com"}
EVENT = "EVR-AAAAAAAA"
MAIN_HALL = {
    "name": "Main Hall",
    "location": "Level 1",
    "capacity": 300,
    "supported_layouts": ["theatre"],
    "facilities": ["projector"],
    "accessibility_features": ["wheelchair_access"],
}
#: The Safety Officer's note on each of SCRUM-98 AC2's seven items.
CHECKLIST = {
    "attendance_vs_capacity": "250 expected in a hall for 300.",
    "venue_layout": "Theatre layout, aisles clear.",
    "emergency_access": "Two exits, both signed.",
    "accessibility": "Step-free entrance confirmed.",
    "equipment_placement": "No equipment.",
    "crowd_movement": "One-way flow at the doors.",
    "venue_restrictions": "No open flames.",
}
ONE_PLACE = {"registration_enabled": True, "registration_capacity": 1}
SETTINGS_PATH = f"/api/events/requests/{EVENT}/registration"


def _body(response: TestResponse, expected_status: int) -> Any:
    """The response's JSON, once its status is the one expected."""
    body = response.get_json()
    assert response.status_code == expected_status, body
    return body


def _create_staff(account: dict[str, str], role: Role, session: Session) -> int:
    """Create a staff account as staff are created (ADR-0023); return its user id."""
    user = create_staff_user({**account, "password": PASSWORD, "role": role.value}, session=session)
    return user.id


def _staff_actor(account: dict[str, str], role: Role, session: Session, sign_in: SignIn) -> Actor:
    """Create a staff account and sign it in."""
    _create_staff(account, role, session)
    return sign_in(account["email"], PASSWORD)


def _attendee(name: str, client: FlaskClient, sign_in: SignIn) -> Actor:
    """An Attendee who registered an account (SCRUM-52), signed in."""
    email = f"{name.lower()}@example.com"
    account = {
        "full_name": name,
        "email": email,
        "password": PASSWORD,
        "role": Role.ATTENDEE.value,
    }
    _body(client.post("/api/auth/register", json=account), 201)
    return sign_in(email, PASSWORD)


def _my_registration_statuses(attendee: Actor) -> list[str]:
    """The statuses of the attendee's own upcoming registrations."""
    listed = _body(attendee.get("/api/events/registrations"), 200)["registrations"]
    return [row["status"] for row in listed]


def _book_the_hall(coordinator: Actor, venue_staff: Actor, event_day: str) -> None:
    """Book the Main Hall for the event's morning, and have Venue Staff approve it."""
    hall = _body(venue_staff.post("/api/venues", MAIN_HALL), 201)
    booking = {
        "venue_id": hall["id"],
        "starts_at": f"{event_day}T09:00:00+08:00",
        "ends_at": f"{event_day}T12:00:00+08:00",
        "purpose": "Partner summit",
    }
    bookings_path = f"/api/venues/events/{EVENT}/booking-requests"
    arrangement = _body(coordinator.post(bookings_path, booking), 201)
    decision_path = f"/api/venues/booking-requests/{arrangement['id']}/decision"
    approved = _body(venue_staff.post(decision_path, {"outcome": "approved"}), 200)
    assert approved["status"] == "approved"


def _pass_safety_check(coordinator: Actor, safety_officer: Actor) -> None:
    """Send the event to Safety Review and have the Safety Officer approve it."""
    sent = _body(coordinator.post(f"/api/events/requests/{EVENT}/safety-review"), 200)
    assert sent["status"] == "safety_review"
    approval = {"outcome": "approved", "checklist": CHECKLIST}
    _body(safety_officer.post(f"/api/events/requests/{EVENT}/safety-outcome", approval), 200)


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
) -> int:
    """An approved event, assigned to the coordinator; returns its id."""
    event_request = make_event_request(
        reference=EVENT,
        status=EventRequestStatus.APPROVED,
        coordinator_id=coordinator_id,
        proposed_date=date.fromisoformat(event_day),
    )
    db_session.add(event_request)
    db_session.commit()
    return event_request.id


def test_one_place_passes_from_one_attendee_to_another(
    client: FlaskClient,
    sign_in: SignIn,
    coordinator: Actor,
    venue_staff: Actor,
    safety_officer: Actor,
    approved_event: int,
    event_day: str,
) -> None:
    registrations_path = f"/api/events/catalogue/{approved_event}/registrations"
    alice = _attendee("Alice", client, sign_in)
    bob = _attendee("Bob", client, sign_in)

    # --- Registration can't open before the event is confirmed (SCRUM-69 AC4) ---
    too_early = _body(coordinator.patch(SETTINGS_PATH, ONE_PLACE), 409)
    assert (too_early["error"], too_early["message"]) == (
        "registration_not_enablable",
        "Registration can be enabled only for a confirmed event.",
    )

    # --- A venue is booked and approved, and the event passes its safety check
    # --- (SCRUM-42, SCRUM-43, SCRUM-97, SCRUM-98) ---
    _book_the_hall(coordinator, venue_staff, event_day)
    _pass_safety_check(coordinator, safety_officer)

    # --- The coordinator confirms it (SCRUM-49 AC1) ---
    confirmed = _body(coordinator.post(f"/api/events/requests/{EVENT}/confirm"), 200)
    assert confirmed["status"] == "confirmed"

    # --- The coordinator opens registration with one place (SCRUM-69 AC1) ---
    settings = _body(coordinator.patch(SETTINGS_PATH, ONE_PLACE), 200)
    assert (settings["registration_enabled"], settings["registration_capacity"]) == (True, 1)

    # --- A registers, and sees it in their list (SCRUM-52 AC2, AC5) ---
    registered = _body(alice.post(registrations_path), 201)
    assert registered["status"] == "registered"
    assert _my_registration_statuses(alice) == ["registered"]

    # --- B is turned away: the event is full (SCRUM-54 AC2) ---
    full = _body(bob.post(registrations_path), 409)
    assert full["error"] == "event_full"
    assert _my_registration_statuses(bob) == []

    # --- A withdraws; the row stays, marked withdrawn (SCRUM-53 AC2) ---
    withdrawn = _body(alice.delete(registrations_path), 200)
    assert withdrawn["status"] == "withdrawn"
    assert _my_registration_statuses(alice) == ["withdrawn"]

    # --- The place is free, so B takes it (SCRUM-53 AC2, SCRUM-54 AC2) ---
    assert _body(bob.post(registrations_path), 201)["status"] == "registered"
    assert _my_registration_statuses(bob) == ["registered"]

    # --- A registers again, and finds it gone (ADR-0032) ---
    refused_again = _body(alice.post(registrations_path), 409)
    assert refused_again["error"] == "event_full"
    assert _my_registration_statuses(alice) == ["withdrawn"]
