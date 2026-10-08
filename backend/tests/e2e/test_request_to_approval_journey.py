"""SCRUM-41: one event request, walked from draft to approval through the API.

An organiser drafts a request and submits it. A coordinator is assigned, reviews it,
asks a question, and can't approve it until the organiser answers. The organiser
answers and amends the attendance, and the coordinator approves. Every call goes
through the real routes with Flask's test client (ADR-0031), so this proves that the
stories fit together, not only that each one works on its own.

The user stories and acceptance criteria it exercises (SCRUM-41 AC3):

- SCRUM-19 "submit an event request": AC5.
- SCRUM-20 "save and resume a draft event request": AC1, AC3, AC4.
- SCRUM-24 "see the events my role is involved in": AC9.
- SCRUM-30 "assign a coordinator to a submitted event": AC1, AC3, AC4, AC5.
- SCRUM-31 "review and decide a submitted request": AC1, AC2, AC3, AC4, AC8, AC9, AC10.
- SCRUM-32 "ask the organiser for clarification": AC1, AC2, AC3, AC4.
- SCRUM-33 "update event information and flag significant changes": AC4, AC5.
- SCRUM-39 "be notified about review and approval decisions": AC1, AC2, AC3, AC4.

Each step's banner comment names the ones it covers. It runs with the rest of the
suite in CI, so a broken journey fails the backend check (SCRUM-41 AC2).
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

pytestmark = [pytest.mark.scrum_41, pytest.mark.e2e]

#: Each account's name and email, as the event record shows a coordinator's contact.
COORDINATOR_ACCOUNT = {"full_name": "Carl Coordinator", "email": "carl@example.com"}
ORGANISER_ACCOUNT = {"full_name": "Olivia Organiser", "email": "olivia@acme.example"}
ORGANISATION = {
    "name": "Acme Events",
    "contact_name": "Olivia Organiser",
    "contact_email": "olivia@acme.example",
}

EVENT_NAME = "Partner Summit"
CLARIFICATION_QUESTION = "Will any guests need step-free access?"
CLARIFICATION_RESPONSE = "Yes, two guests use wheelchairs, and 50 more partners are coming."
APPROVAL = {"outcome": "approved"}

REQUESTS_PATH = "/api/events/requests"
DRAFTS_PATH = f"{REQUESTS_PATH}/drafts"


def _body(response: TestResponse, expected_status: int) -> dict[str, Any]:
    """The response's JSON, once its status is the one expected."""
    body = response.get_json()
    assert response.status_code == expected_status, body
    return body


def _latest_notification(actor: Actor) -> tuple[str, str | None] | None:
    """The kind and detail of the actor's newest notification, or ``None`` if none."""
    notifications = _body(actor.get("/api/notifications"), 200)["notifications"]
    if not notifications:
        return None
    latest = notifications[0]
    return latest["kind"], latest["detail"]


def _record(actor: Actor, reference: str) -> dict[str, Any]:
    """The request's record, as the actor sees."""
    return _body(actor.get(f"{REQUESTS_PATH}/{reference}"), 200)


def _history_kinds(actor: Actor, reference: str) -> list[str]:
    """The kinds of the request's history entries the actor sees, oldest first."""
    history = _body(actor.get(f"{REQUESTS_PATH}/{reference}/history"), 200)["history"]
    return [entry["kind"] for entry in history]


@pytest.fixture()
def password(valid_registration_payload: dict[str, Any]) -> str:
    """A password the policy accepts, shared by both accounts (ADR-0005)."""
    return valid_registration_payload["password"]


@pytest.fixture()
def coordinator(db_session: Session, sign_in: SignIn, password: str) -> Actor:
    """The only Event Coordinator, created as staff are (ADR-0023) and signed in."""
    create_staff_user(
        {**COORDINATOR_ACCOUNT, "password": password, "role": Role.EVENT_COORDINATOR.value},
        session=db_session,
    )
    return sign_in(COORDINATOR_ACCOUNT["email"], password)


@pytest.fixture()
def organiser(client: FlaskClient, coordinator: Actor, sign_in: SignIn, password: str) -> Actor:
    """An Event Organiser who registered with their organisation, signed in.

    The coordinator records the organisation first, since only staff may (SCRUM-66).
    """
    organisation = _body(coordinator.post("/api/organisations", ORGANISATION), 201)
    registration = {
        **ORGANISER_ACCOUNT,
        "password": password,
        "role": Role.EVENT_ORGANISER.value,
        "organisation_id": organisation["id"],
    }
    _body(client.post("/api/auth/register", json=registration), 201)
    return sign_in(ORGANISER_ACCOUNT["email"], password)


def test_a_request_travels_from_draft_to_approval(organiser: Actor, coordinator: Actor) -> None:
    # --- 1. Draft: saved with only a name, then completed (SCRUM-20 AC1, AC3, AC4) ---
    draft = _body(organiser.post(DRAFTS_PATH, {"name": EVENT_NAME}), 201)
    reference = draft["reference"]
    request_path = f"{REQUESTS_PATH}/{reference}"
    assert draft["status"] == "draft"
    assert reference.startswith("EVR-")

    details = {
        "proposed_date": (local_today() + timedelta(days=30)).isoformat(),
        "start_time": "09:00",
        "end_time": "17:00",
        "expected_attendance": 250,
    }
    completed = _body(organiser.patch(f"{DRAFTS_PATH}/{reference}", details), 200)
    assert completed["status"] == "draft"
    assert coordinator.get(request_path).status_code == 404

    # --- 2. Submission: listed for the organiser as submitted (SCRUM-19 AC5) ---
    _body(organiser.post(f"{DRAFTS_PATH}/{reference}/submit"), 200)
    listed = _body(organiser.get(REQUESTS_PATH), 200)["event_requests"]
    assert [(row["reference"], row["status"]) for row in listed] == [(reference, "submitted")]

    # --- 3. Assignment: the only coordinator gets it, and both sides are told ---
    # (SCRUM-30 AC1, AC3-AC5; SCRUM-24 AC9; SCRUM-31 AC2; SCRUM-39 AC1, AC4)
    assert _record(organiser, reference)["coordinator"] == COORDINATOR_ACCOUNT
    assert _record(coordinator, reference)["expected_attendance"] == 250
    assigned = _body(coordinator.get(f"{REQUESTS_PATH}/assigned"), 200)["event_requests"]
    assert [row["reference"] for row in assigned] == [reference]
    assert _latest_notification(coordinator) == ("coordinator_assigned", None)
    assert _latest_notification(organiser) == ("request_assigned", None)

    # --- 4. Review (SCRUM-31 AC3) ---
    reviewed = _body(coordinator.post(f"{request_path}/review"), 200)
    assert reviewed["status"] == "under_review"

    # --- 5. Clarification: the organiser is asked, and approval is refused ---
    # (SCRUM-32 AC1, AC3; SCRUM-39 AC2)
    question = {"message": CLARIFICATION_QUESTION}
    asked = _body(coordinator.post(f"{request_path}/request-clarification", question), 200)
    assert asked["status"] == "awaiting_clarification"
    assert _latest_notification(organiser) == ("clarification_requested", CLARIFICATION_QUESTION)

    refused = _body(coordinator.post(f"{request_path}/decide", APPROVAL), 409)
    assert refused["error"] == "clarification_outstanding"

    # --- 6. Resubmission: answered, with more attendees ---
    # (SCRUM-32 AC2; SCRUM-39 AC2)
    answer = {"response": CLARIFICATION_RESPONSE, "expected_attendance": 300}
    resubmitted = _body(organiser.post(f"{request_path}/resubmit", answer), 200)
    assert (resubmitted["status"], resubmitted["expected_attendance"]) == ("under_review", 300)
    assert _latest_notification(coordinator) == ("clarification_answered", CLARIFICATION_RESPONSE)

    # --- 7. Approval, and what the organiser sees afterwards ---
    # (SCRUM-31 AC1, AC4, AC8-AC10; SCRUM-32 AC4; SCRUM-33 AC4, AC5; SCRUM-39 AC3)
    approved = _body(coordinator.post(f"{request_path}/decide", APPROVAL), 200)
    assert approved["status"] == "approved"

    record = _record(organiser, reference)
    assert record["expected_attendance"] == 300
    decision = record["decision"]
    assert (decision["outcome"], decision["reason"], decision["decided_by"]) == (
        "approved",
        None,
        "Carl Coordinator",
    )
    [clarification] = record["clarifications"]
    assert clarification["message"] == CLARIFICATION_QUESTION
    assert clarification["requested_by"] == "Carl Coordinator"
    assert clarification["response"] == CLARIFICATION_RESPONSE
    assert clarification["answered_by"] == "Olivia Organiser"
    assert _latest_notification(organiser) == ("event_request_approved", None)
    assert _history_kinds(organiser, reference) == [
        "coordinator_assigned",
        "review_started",
        "clarification_requested",
        "field_changed",
        "clarification_answered",
        "decision_recorded",
    ]
