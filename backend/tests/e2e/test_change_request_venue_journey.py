"""SCRUM-58 AC8: an approved change unsettles a Confirmed event, through the API.

A Confirmed event, walked there through the routes, has a venue booked, a reservation
of equipment and the Safety Officer's approval. Its Organiser asks to move it a week
later, and its coordinator approves. The booking is marked Requires reconfirmation
(AC1), the reservation is marked for reassessment (SCRUM-60 AC1), the safety approval is
withdrawn (AC6) and the event is back to Approved (AC7), and it can't go on while either
is marked (AC3). Venue Staff and Technical Support are told. Venue Staff reconfirm the
booking for the new period (SCRUM-59), Technical Support confirm the reservation
(SCRUM-60 AC3), and the event passes a new Safety Review and is confirmed again
(SCRUM-97, SCRUM-49). Every call goes through the real routes with Flask's test client
(ADR-0031).

The event is saved as approved, with its coordinator: the request-to-approval journey
is test_request_to_approval_journey.py. Dates are counted from today, so the journey
never falls into the past. The Organiser registers through the routes, with their
organisation, so the event can be theirs.
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

pytestmark = [pytest.mark.scrum_58, pytest.mark.e2e]

PASSWORD = "Password123"
COORDINATOR_ACCOUNT = {"full_name": "Cara Coordinator", "email": "cara@example.com"}
VENUE_STAFF_ACCOUNT = {"full_name": "Vera Venue", "email": "vera@example.com"}
TECHNICAL_SUPPORT_ACCOUNT = {"full_name": "Tina Technician", "email": "tina@example.com"}
SAFETY_OFFICER_ACCOUNT = {"full_name": "Sam Safety", "email": "sam@example.com"}
ORGANISER_ACCOUNT = {"full_name": "Olivia Organiser", "email": "olivia@acme.example"}
ORGANISATION = {
    "name": "Acme Events",
    "contact_name": "Olivia Organiser",
    "contact_email": "olivia@acme.example",
}
EVENT = "EVR-AAAAAAAA"
EVENT_PATH = f"/api/events/requests/{EVENT}"
SAFETY_REVIEW_PATH = f"{EVENT_PATH}/safety-review"
SAFETY_OUTCOME_PATH = f"{EVENT_PATH}/safety-outcome"
CONFIRM_PATH = f"{EVENT_PATH}/confirm"
BOOKINGS_PATH = f"/api/venues/events/{EVENT}/booking-requests"
RESERVATIONS_PATH = f"/api/equipment/events/{EVENT}/reservations"
REASSESSMENTS_PATH = f"/api/equipment/events/{EVENT}/reassessments"
MAIN_HALL = {
    "name": "Main Hall",
    "location": "Level 1",
    "capacity": 300,
    "supported_layouts": ["theatre"],
    "facilities": ["projector"],
    "accessibility_features": ["wheelchair_access"],
}
PROJECTORS = {"name": "Projector", "total_quantity": 10, "store_name": "Central AV store"}
CHECKLIST = {
    "attendance_vs_capacity": "250 expected in a hall for 300.",
    "venue_layout": "Theatre layout, aisles clear.",
    "emergency_access": "Two exits, both signed.",
    "accessibility": "Step-free entrance confirmed.",
    "equipment_placement": "Projector cables taped down.",
    "crowd_movement": "One-way flow at the doors.",
    "venue_restrictions": "No open flames.",
}
SAFETY_APPROVAL = {"outcome": "approved", "checklist": CHECKLIST}
TIMING_REASON = "The event's date or time changed."


def _body(response: TestResponse, expected_status: int) -> Any:
    """The response's JSON, once its status is the one expected."""
    body = response.get_json()
    assert response.status_code == expected_status, body
    return body


def _staff_id(account: dict[str, str], role: Role, session: Session) -> int:
    """Create a staff account as staff are created (ADR-0023); return its user id."""
    user = create_staff_user({**account, "password": PASSWORD, "role": role.value}, session=session)
    return user.id


def _staff_actor(account: dict[str, str], role: Role, session: Session, sign_in: SignIn) -> Actor:
    """Create a staff account and sign it in."""
    _staff_id(account, role, session)
    return sign_in(account["email"], PASSWORD)


def _latest_notification(actor: Actor) -> tuple[str, str | None]:
    """The kind and detail of the actor's newest notification."""
    latest = _body(actor.get("/api/notifications"), 200)["notifications"][0]
    return latest["kind"], latest["detail"]


def _event_status(actor: Actor) -> str:
    return _body(actor.get(EVENT_PATH), 200)["status"]


def _pass_safety_review_and_confirm(coordinator: Actor, safety_officer: Actor) -> None:
    """Send the event to Safety Review, have it approved, and confirm it."""
    _body(coordinator.post(SAFETY_REVIEW_PATH), 200)
    _body(safety_officer.post(SAFETY_OUTCOME_PATH, SAFETY_APPROVAL), 200)
    assert _body(coordinator.post(CONFIRM_PATH), 200)["status"] == "confirmed"


@pytest.fixture()
def coordinator_id(db_session: Session) -> int:
    return _staff_id(COORDINATOR_ACCOUNT, Role.EVENT_COORDINATOR, db_session)


@pytest.fixture()
def coordinator(coordinator_id: int, sign_in: SignIn) -> Actor:
    return sign_in(COORDINATOR_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def venue_staff(db_session: Session, sign_in: SignIn) -> Actor:
    return _staff_actor(VENUE_STAFF_ACCOUNT, Role.VENUE_STAFF, db_session, sign_in)


@pytest.fixture()
def technical_support(db_session: Session, sign_in: SignIn) -> Actor:
    return _staff_actor(
        TECHNICAL_SUPPORT_ACCOUNT, Role.TECHNICAL_SUPPORT_STAFF, db_session, sign_in
    )


@pytest.fixture()
def safety_officer(db_session: Session, sign_in: SignIn) -> Actor:
    return _staff_actor(SAFETY_OFFICER_ACCOUNT, Role.SAFETY_OFFICER, db_session, sign_in)


@pytest.fixture()
def organiser_ids(client: FlaskClient, coordinator: Actor) -> tuple[int, int]:
    """The Organiser's user id and organisation id, registered through the routes."""
    organisation = _body(coordinator.post("/api/organisations", ORGANISATION), 201)
    account = {
        **ORGANISER_ACCOUNT,
        "password": PASSWORD,
        "role": Role.EVENT_ORGANISER.value,
        "organisation_id": organisation["id"],
    }
    registered = _body(client.post("/api/auth/register", json=account), 201)
    return registered["id"], organisation["id"]


@pytest.fixture()
def organiser(organiser_ids: tuple[int, int], sign_in: SignIn) -> Actor:
    return sign_in(ORGANISER_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def event_day() -> date:
    """The day of the event, a month away."""
    return local_today() + timedelta(days=30)


@pytest.fixture()
def approved_event(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    coordinator_id: int,
    organiser_ids: tuple[int, int],
    event_day: date,
) -> None:
    """The Organiser's approved event, a month away, assigned to the coordinator."""
    organiser_id, organisation_id = organiser_ids
    event_request = make_event_request(
        reference=EVENT,
        status=EventRequestStatus.APPROVED,
        organiser_id=organiser_id,
        organisation_id=organisation_id,
        coordinator_id=coordinator_id,
        proposed_date=event_day,
    )
    db_session.add(event_request)
    db_session.commit()


def test_a_confirmed_events_approved_date_change_goes_back_through_venue_staff(
    coordinator: Actor,
    organiser: Actor,
    venue_staff: Actor,
    technical_support: Actor,
    safety_officer: Actor,
    approved_event: None,
    event_day: date,
) -> None:
    # --- The event has a venue and equipment, and is confirmed through the routes ---
    hall = _body(venue_staff.post("/api/venues", MAIN_HALL), 201)
    booking_request = {
        "venue_id": hall["id"],
        "starts_at": f"{event_day.isoformat()}T09:00:00+08:00",
        "ends_at": f"{event_day.isoformat()}T12:00:00+08:00",
        "purpose": "Partner summit",
    }
    booking = _body(coordinator.post(BOOKINGS_PATH, booking_request), 201)
    decision_path = f"/api/venues/booking-requests/{booking['id']}/decision"
    _body(venue_staff.post(decision_path, {"outcome": "approved"}), 200)

    projectors = _body(technical_support.post("/api/equipment/types", PROJECTORS), 201)
    line_request = {"equipment_type_id": projectors["id"], "quantity": 2}
    line = _body(coordinator.post(f"{EVENT_PATH}/equipment", line_request), 201)
    _body(technical_support.post(RESERVATIONS_PATH, line_request), 201)
    outcome_path = f"{EVENT_PATH}/equipment/{line['id']}/outcome"
    _body(technical_support.post(outcome_path, {"provided_quantity": 2}), 200)

    _pass_safety_review_and_confirm(coordinator, safety_officer)
    assert _event_status(coordinator) == "confirmed"

    # --- The Organiser asks to move it a week on; the coordinator approves ---
    new_day = event_day + timedelta(days=7)
    change = {"proposed_date": new_day.isoformat(), "reason": "The keynote moved."}
    raised = _body(organiser.post(f"{EVENT_PATH}/change-requests", change), 201)
    decide_path = f"{EVENT_PATH}/change-requests/{raised['id']}/decide"
    approved = _body(coordinator.post(decide_path, {"outcome": "approved"}), 200)
    assert approved["status"] == "approved"

    # --- The booking is marked Requires reconfirmation, and stays Approved (AC1) ---
    [marked] = _body(coordinator.get(BOOKINGS_PATH), 200)
    assert (marked["status"], marked["flagged_after_change"]) == ("approved", True)
    assert marked["reassessment_flags"] == [
        {"kind": "requires_reconfirmation", "reason": TIMING_REASON}
    ]

    # --- The reservation is marked, held for its old period (SCRUM-60 AC1) ---
    [to_reassess] = _body(technical_support.get(REASSESSMENTS_PATH), 200)
    assert to_reassess["equipment_type_id"] == projectors["id"]
    assert to_reassess["reservations"][0]["starts_at"] == (
        f"{event_day.isoformat()}T09:00:00+08:00"
    )

    # --- Venue Staff and Technical Support are told (AC1, SCRUM-60) ---
    assert _latest_notification(venue_staff) == (
        "significant_change",
        f"Venue arrangement {booking['id']} at Main Hall: {TIMING_REASON}",
    )
    assert _latest_notification(technical_support)[0] == "significant_change"

    # --- The approval is withdrawn and the event is back to Approved (AC6, AC7) ---
    assert _event_status(coordinator) == "approved"
    assert _body(coordinator.get(f"{EVENT_PATH}/history"), 200)["history"][-1]["details"] == {
        "significant_fields": ["proposed_date", "end_date"]
    }

    # --- It can't go on while anything is marked (AC3) ---
    assert _body(coordinator.post(CONFIRM_PATH), 409)["error"] == "confirmation_not_allowed"
    refused = _body(coordinator.post(SAFETY_REVIEW_PATH), 409)
    assert refused["details"]["venue_arrangements"] == [
        f"Venue arrangement {booking['id']} is flagged (requires reconfirmation): {TIMING_REASON}"
    ]
    assert len(refused["details"]["equipment"]) == 1

    # --- Venue Staff see it, a week later, and reconfirm it (SCRUM-59 AC1, AC2) ---
    [flagged] = _body(venue_staff.get("/api/venues/booking-requests/flagged"), 200)
    assert flagged["booking"]["id"] == booking["id"]
    new_period = flagged["reconfirm_with"]
    assert new_period["starts_at"] == f"{new_day.isoformat()}T09:00:00+08:00"
    assert new_period["ends_at"] == f"{new_day.isoformat()}T12:00:00+08:00"
    reconfirm_path = f"/api/venues/booking-requests/{booking['id']}/reconfirm"
    period = {"starts_at": new_period["starts_at"], "ends_at": new_period["ends_at"]}
    reconfirmed = _body(venue_staff.post(reconfirm_path, period), 200)
    assert (reconfirmed["flagged_after_change"], reconfirmed["reassessment_flags"]) == (False, [])
    assert _latest_notification(coordinator)[0] == "venue_booking_reconfirmed"

    # --- The reservation still holds the event back, until Technical Support act ---
    still_refused = _body(coordinator.post(SAFETY_REVIEW_PATH), 409)
    assert list(still_refused["details"]) == ["equipment"]
    confirm_move_path = f"{REASSESSMENTS_PATH}/{projectors['id']}/confirm"
    [moved] = _body(technical_support.post(confirm_move_path), 200)
    assert moved["starts_at"] == f"{new_day.isoformat()}T09:00:00+08:00"

    # --- A new Safety Review, then it is confirmed again (AC7, SCRUM-97, SCRUM-49) ---
    _pass_safety_review_and_confirm(coordinator, safety_officer)
    assert _event_status(organiser) == "confirmed"
