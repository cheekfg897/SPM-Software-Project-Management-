"""SCRUM-56: an organiser asks for a change to their submitted event, through the API.

An organiser submits an event, and the Event Coordinator Lead gives it to a coordinator.
The organiser asks for a later start and more attendees, saying why: the request is on
the record as Pending, the event keeps its details, and the coordinator is told what
should change and why. A second request is refused while the first waits. The
organiser withdraws the first, the coordinator is told, and a new request is taken.
Every call goes through the real routes with Flask's test client (ADR-0031), so the
login, the role checks, the JSON parsing and the error handlers run as for a browser.

The acceptance criteria it exercises: SCRUM-56 AC1, AC2, AC3, AC4, AC5, AC7 and AC8.
Each step's banner comment names the ones it covers.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session
from werkzeug.test import TestResponse

from app.common.clock import local_today
from app.modules.auth.permissions import Role
from app.modules.auth.services import create_staff_user
from tests.e2e.actors import Actor, SignIn

pytestmark = [pytest.mark.scrum_56, pytest.mark.e2e]

PASSWORD = "Password123"
COORDINATOR_ACCOUNT = {"full_name": "Carl Coordinator", "email": "carl@example.com"}
LEAD_ACCOUNT = {"full_name": "Leah Lead", "email": "leah@example.com"}
ORGANISER_ACCOUNT = {"full_name": "Olivia Organiser", "email": "olivia@acme.example"}
ORGANISATION = {
    "name": "Acme Events",
    "contact_name": "Olivia Organiser",
    "contact_email": "olivia@acme.example",
}
REQUESTS_PATH = "/api/events/requests"
REASON = "Our keynote speaker lands at 9:30, and more partners said yes."
LATER_AND_BIGGER = {"start_time": "10:00", "expected_attendance": 300, "reason": REASON}
ALREADY_PENDING_MESSAGE = (
    "A change request is already waiting for the coordinator. Withdraw it, or wait for "
    "their decision, before raising another."
)


def _body(response: TestResponse, expected_status: int) -> Any:
    """The response's JSON, once its status is the one expected."""
    body = response.get_json()
    assert response.status_code == expected_status, body
    return body


def _latest_notification(actor: Actor) -> tuple[str, str | None]:
    """The kind and detail of the actor's newest notification."""
    latest = _body(actor.get("/api/notifications"), 200)["notifications"][0]
    return latest["kind"], latest["detail"]


def _staff(account: dict[str, str], role: Role, session: Session, sign_in: SignIn) -> Actor:
    """A staff account, created as staff are (ADR-0023), signed in."""
    create_staff_user({**account, "password": PASSWORD, "role": role.value}, session=session)
    return sign_in(account["email"], PASSWORD)


@pytest.fixture()
def coordinator(db_session: Session, sign_in: SignIn) -> Actor:
    """The only Event Coordinator, signed in."""
    return _staff(COORDINATOR_ACCOUNT, Role.EVENT_COORDINATOR, db_session, sign_in)


@pytest.fixture()
def lead(db_session: Session, sign_in: SignIn) -> Actor:
    """The Event Coordinator Lead, signed in."""
    return _staff(LEAD_ACCOUNT, Role.EVENT_COORDINATOR_LEAD, db_session, sign_in)


@pytest.fixture()
def organiser(client: FlaskClient, coordinator: Actor, sign_in: SignIn) -> Actor:
    """An Event Organiser who registered with their organisation, signed in.

    The coordinator records the organisation first, since only staff may (SCRUM-66).
    """
    organisation = _body(coordinator.post("/api/organisations", ORGANISATION), 201)
    registration = {
        **ORGANISER_ACCOUNT,
        "password": PASSWORD,
        "role": Role.EVENT_ORGANISER.value,
        "organisation_id": organisation["id"],
    }
    _body(client.post("/api/auth/register", json=registration), 201)
    return sign_in(ORGANISER_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def reference(organiser: Actor, lead: Actor) -> str:
    """The organiser's submitted event, a month away, assigned to the coordinator."""
    details = {
        "name": "Partner Summit",
        "proposed_date": (local_today() + timedelta(days=30)).isoformat(),
        "start_time": "09:00",
        "end_time": "17:00",
        "expected_attendance": 250,
    }
    submitted = _body(organiser.post(REQUESTS_PATH, details), 201)
    assignment = {"coordinator_email": COORDINATOR_ACCOUNT["email"]}
    _body(lead.post(f"{REQUESTS_PATH}/{submitted['reference']}/coordinator", assignment), 200)
    return submitted["reference"]


def test_a_change_is_asked_for_refused_while_waiting_withdrawn_and_asked_again(
    organiser: Actor, coordinator: Actor, reference: str
) -> None:
    record_path = f"{REQUESTS_PATH}/{reference}"
    change_requests_path = f"{record_path}/change-requests"

    # --- 1. Asked for: Pending on the record, the event as it was (AC1-AC4) ---
    first = _body(organiser.post(change_requests_path, LATER_AND_BIGGER), 201)
    assert first["status"] == "pending"
    assert first["changes"] == [
        {"field": "start_time", "previous_value": "09:00:00", "requested_value": "10:00:00"},
        {"field": "expected_attendance", "previous_value": 250, "requested_value": 300},
    ]
    record = _body(organiser.get(record_path), 200)
    assert record["change_requests"] == [first]
    assert (record["start_time"], record["expected_attendance"]) == ("09:00:00", 250)

    # --- 2. The coordinator is told what should change and why (AC5) ---
    assert _latest_notification(coordinator) == (
        "change_request_raised",
        f"Changes to start time, expected attendance. Reason: {REASON}",
    )
    assert _body(coordinator.get(record_path), 200)["change_requests"] == [first]

    # --- 3. A second waits for the first (AC7) ---
    refused = _body(organiser.post(change_requests_path, LATER_AND_BIGGER), 409)
    assert refused == {"error": "conflict", "message": ALREADY_PENDING_MESSAGE}

    # --- 4. Withdrawn, and the coordinator is told (AC8) ---
    withdraw_path = f"{change_requests_path}/{first['id']}/withdraw"
    withdrawn = _body(organiser.post(withdraw_path), 200)
    assert withdrawn["status"] == "withdrawn"
    assert withdrawn["withdrawn_at"] is not None
    assert _latest_notification(coordinator) == ("change_request_withdrawn", None)
    assert _body(organiser.post(withdraw_path), 409)["error"] == "change_request_not_pending"

    # --- 5. Asked for again, now nothing waits (AC7) ---
    second = _body(organiser.post(change_requests_path, LATER_AND_BIGGER), 201)
    listed = _body(organiser.get(record_path), 200)["change_requests"]
    assert [each["status"] for each in listed] == ["withdrawn", "pending"]
    assert second["id"] != first["id"]
