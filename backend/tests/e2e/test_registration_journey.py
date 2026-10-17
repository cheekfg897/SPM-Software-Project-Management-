"""SCRUM-53: attendees take and give up the one place at an event, through the API.

The coordinator opens registration with room for one. Attendee A registers and sees it
in their list. Attendee B is turned away because the event is full (SCRUM-54 AC2). When
A withdraws, the place is free and B takes it, and A, registering again, finds it gone
(SCRUM-53 AC2, ADR-0032). Every call goes through the real routes with Flask's test
client (ADR-0031).

The Event Organiser's list of registrants is SCRUM-55's route, which is not on main
yet; add it here when it lands (the organiser sees A withdrawn and B registered).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
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
EVENT = "EVR-AAAAAAAA"
ONE_PLACE = {"registration_enabled": True, "registration_capacity": 1}


def _body(response: TestResponse, expected_status: int) -> Any:
    """The response's JSON, once its status is the one expected."""
    body = response.get_json()
    assert response.status_code == expected_status, body
    return body


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


@pytest.fixture()
def coordinator_id(db_session: Session) -> int:
    """The Event Coordinator's user id; the event is assigned to them."""
    account = {**COORDINATOR_ACCOUNT, "password": PASSWORD, "role": Role.EVENT_COORDINATOR.value}
    return create_staff_user(account, session=db_session).id


@pytest.fixture()
def coordinator(coordinator_id: int, sign_in: SignIn) -> Actor:
    """The Event Coordinator, signed in."""
    return sign_in(COORDINATOR_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def confirmed_event(
    db_session: Session, make_event_request: Callable[..., EventRequest], coordinator_id: int
) -> int:
    """A confirmed event a month away, assigned to the coordinator; returns its id.

    Saved as confirmed directly: nothing confirms events until SCRUM-49.
    """
    event_request = make_event_request(
        reference=EVENT,
        status=EventRequestStatus.CONFIRMED,
        coordinator_id=coordinator_id,
        proposed_date=local_today() + timedelta(days=30),
    )
    db_session.add(event_request)
    db_session.commit()
    return event_request.id


def test_one_place_passes_from_one_attendee_to_another(
    client: FlaskClient, sign_in: SignIn, coordinator: Actor, confirmed_event: int
) -> None:
    registrations_path = f"/api/events/catalogue/{confirmed_event}/registrations"
    alice = _attendee("Alice", client, sign_in)
    bob = _attendee("Bob", client, sign_in)

    # --- The coordinator opens registration with one place (SCRUM-69 AC1) ---
    settings = _body(
        coordinator.patch(f"/api/events/requests/{EVENT}/registration", ONE_PLACE), 200
    )
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
