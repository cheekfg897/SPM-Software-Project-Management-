"""SCRUM-92: a booked venue becomes unavailable and the event moves to another one.

An approved event has the Main Hall booked and has passed its safety check. Venue Staff
block the hall over the event's period for equipment failure: the booking is flagged
"Needs Alternative Venue" with the reason and period (AC1, AC2), the event stays in
Safety Review because it was not yet confirmed (AC3), the coordinator is told (AC5) and
can't confirm it (SCRUM-49 AC6). The coordinator searches for the original period and
raises a replacement at the Annex linked to the flagged booking (AC6). Venue Staff
approve it: the hall is released (AC7) and the safety approval is withdrawn, so the
event goes back to planning and must pass a new check before it is confirmed (AC10).
Once confirmed, deactivating the Annex sends the event back to Approved (AC3, AC9), and
reactivating it clears the flag. A second journey removes a block and the flag clears
(AC8). Every call goes through the real routes with Flask's test client (ADR-0031).

The event is saved as approved with its coordinator; the request-to-approval journey is
test_request_to_approval_journey.py. Dates are a month from today, so the journey never
falls into the past.
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

pytestmark = [pytest.mark.scrum_92, pytest.mark.e2e]

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
ANNEX = {**MAIN_HALL, "name": "Annex", "location": "Level 2"}
CHECKLIST = {
    "attendance_vs_capacity": "80 expected in a hall for 300.",
    "venue_layout": "Theatre layout, aisles clear.",
    "emergency_access": "Two exits, both signed.",
    "accessibility": "Step-free entrance confirmed.",
    "equipment_placement": "No equipment.",
    "crowd_movement": "One-way flow at the doors.",
    "venue_restrictions": "No open flames.",
}
BOOKINGS_PATH = f"/api/venues/events/{EVENT}/booking-requests"
SAFETY_REVIEW_PATH = f"/api/events/requests/{EVENT}/safety-review"
SAFETY_OUTCOME_PATH = f"/api/events/requests/{EVENT}/safety-outcome"
CONFIRM_PATH = f"/api/events/requests/{EVENT}/confirm"


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


def _event_status(coordinator: Actor) -> str:
    return _body(coordinator.get(f"/api/events/requests/{EVENT}"), 200)["status"]


def _arrangement(coordinator: Actor, arrangement_id: int) -> dict[str, Any]:
    """One of the event's arrangements, as the coordinator's list shows it."""
    for arrangement in _body(coordinator.get(BOOKINGS_PATH), 200):
        if arrangement["id"] == arrangement_id:
            return arrangement
    raise AssertionError(f"arrangement {arrangement_id} is not listed")


def _latest_notification(actor: Actor) -> tuple[str, str | None]:
    """The kind and detail of the actor's newest notification."""
    newest = _body(actor.get("/api/notifications"), 200)["notifications"][0]
    return newest["kind"], newest["detail"]


def _approve(venue_staff: Actor, arrangement_id: int) -> dict[str, Any]:
    path = f"/api/venues/booking-requests/{arrangement_id}/decision"
    return _body(venue_staff.post(path, {"outcome": "approved"}), 200)


def _pass_safety_check(coordinator: Actor, safety_officer: Actor) -> None:
    """Send the event to Safety Review and have the Safety Officer approve it."""
    _body(coordinator.post(SAFETY_REVIEW_PATH), 200)
    approval = {"outcome": "approved", "checklist": CHECKLIST}
    _body(safety_officer.post(SAFETY_OUTCOME_PATH, approval), 200)


@pytest.fixture()
def coordinator(db_session: Session, sign_in: SignIn) -> Actor:
    return _staff_actor(COORDINATOR_ACCOUNT, Role.EVENT_COORDINATOR, db_session, sign_in)


@pytest.fixture()
def venue_staff(db_session: Session, sign_in: SignIn) -> Actor:
    return _staff_actor(VENUE_STAFF_ACCOUNT, Role.VENUE_STAFF, db_session, sign_in)


@pytest.fixture()
def safety_officer(db_session: Session, sign_in: SignIn) -> Actor:
    return _staff_actor(SAFETY_OFFICER_ACCOUNT, Role.SAFETY_OFFICER, db_session, sign_in)


@pytest.fixture()
def event_day() -> str:
    """The day of the event, a month away, as an ISO date."""
    return (local_today() + timedelta(days=30)).isoformat()


@pytest.fixture()
def booked_event(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    coordinator: Actor,
    venue_staff: Actor,
    event_day: str,
) -> int:
    """An approved event with the Main Hall booked, 09:00 to 12:00; returns its id."""
    coordinator_id = int(_body(coordinator.get("/api/auth/me"), 200)["id"])
    event_request = make_event_request(
        reference=EVENT,
        status=EventRequestStatus.APPROVED,
        coordinator_id=coordinator_id,
        proposed_date=date.fromisoformat(event_day),
    )
    db_session.add(event_request)
    db_session.commit()

    hall = _body(venue_staff.post("/api/venues", MAIN_HALL), 201)
    booking = {
        "venue_id": hall["id"],
        "starts_at": f"{event_day}T09:00:00+08:00",
        "ends_at": f"{event_day}T12:00:00+08:00",
        "purpose": "Partner summit",
    }
    arrangement = _body(coordinator.post(BOOKINGS_PATH, booking), 201)
    _approve(venue_staff, arrangement["id"])
    return arrangement["id"]


def test_a_booked_venue_becomes_unavailable_and_the_event_moves_to_another(
    coordinator: Actor,
    venue_staff: Actor,
    safety_officer: Actor,
    booked_event: int,
    event_day: str,
) -> None:
    hall_booking = _arrangement(coordinator, booked_event)
    _pass_safety_check(coordinator, safety_officer)
    annex = _body(venue_staff.post("/api/venues", ANNEX), 201)

    # --- Venue Staff block the hall for an equipment failure (AC1, AC2) ---
    blocked = {
        "start_time": f"{event_day}T10:00:00+08:00",
        "end_time": f"{event_day}T11:00:00+08:00",
        "category": "equipment_failure",
        "reason": "Lift broken.",
    }
    _body(venue_staff.post(f"/api/venues/{hall_booking['venue_id']}/blocks", blocked), 201)
    flagged = _arrangement(coordinator, booked_event)
    assert flagged["status"] == "approved"
    assert flagged["needs_alternative_venue"] is True
    assert flagged["unavailability"] == [
        {
            "category": "equipment_failure",
            "reason": "Lift broken.",
            "starts_at": f"{event_day}T10:00:00+08:00",
            "ends_at": f"{event_day}T11:00:00+08:00",
        }
    ]

    # --- Not yet confirmed, so it stays in Safety Review (AC3); the coordinator is told
    # --- (AC5) and can't confirm it (SCRUM-49 AC6) ---
    assert _event_status(coordinator) == "safety_review"
    assert _latest_notification(coordinator) == (
        "alternative_venue_needed",
        f"Main Hall is unavailable from {event_day} 10:00 to {event_day} 11:00"
        " (equipment failure): Lift broken.",
    )
    refused = _body(coordinator.post(CONFIRM_PATH), 409)
    assert refused["details"] == {
        "venue_arrangements": [f"Venue arrangement {booked_event} needs an alternative venue."]
    }

    # --- The coordinator searches the original period, raises a replacement (AC6) ---
    search = {
        "start_time": hall_booking["starts_at"],
        "end_time": hall_booking["ends_at"],
        "min_capacity": 80,
    }
    found = _body(coordinator.post("/api/venues/search", search), 200)["results"]
    assert [venue["name"] for venue in found] == ["Annex"]
    replacement = {
        "venue_id": annex["id"],
        "starts_at": hall_booking["starts_at"],
        "ends_at": hall_booking["ends_at"],
        "purpose": "Partner summit",
        "replaces_request_id": booked_event,
    }
    raised = _body(coordinator.post(BOOKINGS_PATH, replacement), 201)
    assert raised["replaces_request_id"] == booked_event

    # --- Venue Staff approve it: the hall is released, the safety approval withdrawn
    # --- and the event back in planning (AC7, AC10) ---
    _approve(venue_staff, raised["id"])
    released = _arrangement(coordinator, booked_event)
    assert (released["status"], released["needs_alternative_venue"]) == ("released", False)
    assert _event_status(coordinator) == "approved"

    # --- A new safety check, then the event is confirmed at the Annex ---
    _pass_safety_check(coordinator, safety_officer)
    assert _body(coordinator.post(CONFIRM_PATH), 200)["status"] == "confirmed"

    # --- Deactivating the Annex sends the event back to Approved (AC3, AC9) ---
    deactivation = {"category": "renovation", "reason": "Closed for a refit."}
    _body(venue_staff.post(f"/api/venues/{annex['id']}/deactivate", deactivation), 200)
    assert _event_status(coordinator) == "approved"
    annex_booking = _arrangement(coordinator, raised["id"])
    assert annex_booking["needs_alternative_venue"] is True
    assert annex_booking["unavailability"][0]["ends_at"] is None
    assert _latest_notification(coordinator)[0] == "alternative_venue_needed"

    # --- Reactivating it clears the flag, and the booking stands (AC8) ---
    _body(venue_staff.post(f"/api/venues/{annex['id']}/reactivate"), 200)
    restored = _arrangement(coordinator, raised["id"])
    assert (restored["status"], restored["needs_alternative_venue"]) == ("approved", False)


def test_removing_the_block_clears_the_flag_and_the_booking_stands(
    coordinator: Actor, venue_staff: Actor, booked_event: int, event_day: str
) -> None:
    venue_id = _arrangement(coordinator, booked_event)["venue_id"]
    blocked = {
        "start_time": f"{event_day}T08:00:00+08:00",
        "end_time": f"{event_day}T18:00:00+08:00",
        "category": "safety_concern",
        "reason": "Ceiling leak.",
    }
    block = _body(venue_staff.post(f"/api/venues/{venue_id}/blocks", blocked), 201)
    assert _arrangement(coordinator, booked_event)["needs_alternative_venue"] is True

    removed = venue_staff.delete(f"/api/venues/{venue_id}/blocks/{block['id']}")

    assert removed.status_code == 204
    cleared = _arrangement(coordinator, booked_event)
    assert (cleared["status"], cleared["needs_alternative_venue"]) == ("approved", False)
    assert cleared["unavailability"] == []
