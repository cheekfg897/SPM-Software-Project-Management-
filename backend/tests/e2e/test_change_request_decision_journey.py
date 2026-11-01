"""SCRUM-57: a change request raised by the Organiser and decided by the coordinator.

Two journeys through the real routes with Flask's test client (ADR-0031):

- **Approved.** A Confirmed event with registration open has one Attendee holding a
  place. The Organiser asks to start later and for more attendees. The coordinator
  sees the request on the record beside the event's current values, approves it, and
  the event carries the new values, each one in the history as the coordinator's
  change. The Organiser is told it was approved and the Attendee that the event has a
  new time. Deciding it again is refused.
- **Rejected.** An Approved event, still in planning. While the Organiser's request is
  Pending, the coordinator can't decide the event itself. The coordinator edits the
  attendance the request also changes, so approving it is refused, naming the field
  then and now, and it stays Pending. Rejecting it needs a reason; once rejected, the
  event is unchanged, the Organiser is told why, and the event can be decided again.

The user stories and acceptance criteria they exercise:

- SCRUM-56 "request a change after submitting": AC1, AC4.
- SCRUM-57 "review and decide a change request": AC1, AC2, AC3, AC4, AC5, AC6, AC7,
  AC8, AC9.
- SCRUM-52 "register for an event": AC1.

The events are saved in the status the journey starts from: the request-to-approval
journey (test_request_to_approval_journey.py) and the registration journey walk an
event there through the routes. The Organiser registers through the routes, with
their organisation, so the event can be theirs.
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

pytestmark = [pytest.mark.scrum_57, pytest.mark.e2e]

PASSWORD = "Password123"
COORDINATOR_ACCOUNT = {"full_name": "Cara Coordinator", "email": "cara@example.com"}
ORGANISER_ACCOUNT = {"full_name": "Olivia Organiser", "email": "olivia@acme.example"}
ATTENDEE_ACCOUNT = {"full_name": "Alice Attendee", "email": "alice@example.com"}
ORGANISATION = {
    "name": "Acme Events",
    "contact_name": "Olivia Organiser",
    "contact_email": "olivia@acme.example",
}
EVENT = "EVR-AAAAAAAA"
EVENT_PATH = f"/api/events/requests/{EVENT}"
CHANGE_REQUESTS_PATH = f"{EVENT_PATH}/change-requests"
LATER_AND_BIGGER = {
    "start_time": "10:00",
    "expected_attendance": 300,
    "reason": "The keynote speaker lands later, and more partners are coming.",
}
APPROVAL = {"outcome": "approved", "reason": "The hall holds 300."}
REJECTION_REASON = "The hall can't hold more than 250."


def _body(response: TestResponse, expected_status: int) -> Any:
    """The response's JSON, once its status is the one expected."""
    body = response.get_json()
    assert response.status_code == expected_status, body
    return body


def _refusal(response: TestResponse) -> dict[str, str]:
    """A 409's error code and message."""
    body = _body(response, 409)
    return {"error": body["error"], "message": body["message"]}


def _latest_notification(actor: Actor) -> tuple[str, str | None]:
    """The kind and detail of the actor's newest notification."""
    latest = _body(actor.get("/api/notifications"), 200)["notifications"][0]
    return latest["kind"], latest["detail"]


def _event_values(actor: Actor) -> tuple[str, int]:
    """The event's start time and expected attendance, as the actor's record shows."""
    record = _body(actor.get(EVENT_PATH), 200)
    return record["start_time"], record["expected_attendance"]


def _decide_path(change_request_id: int) -> str:
    return f"{CHANGE_REQUESTS_PATH}/{change_request_id}/decide"


@pytest.fixture()
def coordinator_id(db_session: Session) -> int:
    """The Event Coordinator's user id, created as staff are (ADR-0023)."""
    account = {**COORDINATOR_ACCOUNT, "password": PASSWORD, "role": Role.EVENT_COORDINATOR.value}
    return create_staff_user(account, session=db_session).id


@pytest.fixture()
def coordinator(coordinator_id: int, sign_in: SignIn) -> Actor:
    """The Event Coordinator, signed in."""
    return sign_in(COORDINATOR_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def organiser_ids(client: FlaskClient, coordinator: Actor) -> tuple[int, int]:
    """The Organiser's user id and organisation id, registered through the routes.

    The coordinator records the organisation first, since only staff may (SCRUM-66).
    """
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
    """The Event Organiser, signed in."""
    return sign_in(ORGANISER_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def save_event(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    coordinator_id: int,
    organiser_ids: tuple[int, int],
) -> Callable[[EventRequestStatus], EventRequest]:
    """Save the Organiser's event, a month away, with the coordinator, in a status."""

    def _save(status: EventRequestStatus) -> EventRequest:
        organiser_id, organisation_id = organiser_ids
        event_request = make_event_request(
            reference=EVENT,
            status=status,
            organiser_id=organiser_id,
            organisation_id=organisation_id,
            coordinator_id=coordinator_id,
            proposed_date=local_today() + timedelta(days=30),
        )
        db_session.add(event_request)
        db_session.commit()
        return event_request

    return _save


def test_an_approved_change_is_applied_and_everyone_is_told(
    client: FlaskClient,
    sign_in: SignIn,
    coordinator: Actor,
    organiser: Actor,
    save_event: Callable[[EventRequestStatus], EventRequest],
) -> None:
    event_request = save_event(EventRequestStatus.CONFIRMED)
    event_request.registration_enabled = True
    event_request.registration_capacity = 300
    event_day = date.isoformat(event_request.proposed_date)
    attendee_account = {**ATTENDEE_ACCOUNT, "password": PASSWORD, "role": Role.ATTENDEE.value}
    _body(client.post("/api/auth/register", json=attendee_account), 201)
    attendee = sign_in(ATTENDEE_ACCOUNT["email"], PASSWORD)

    # --- The Attendee holds a place (SCRUM-52 AC1) ---
    registrations_path = f"/api/events/catalogue/{event_request.id}/registrations"
    assert _body(attendee.post(registrations_path), 201)["status"] == "registered"

    # --- The Organiser raises a change request (SCRUM-56 AC1) ---
    raised = _body(organiser.post(CHANGE_REQUESTS_PATH, LATER_AND_BIGGER), 201)

    # --- The coordinator sees it beside the current values (SCRUM-57 AC1) ---
    [shown] = _body(coordinator.get(EVENT_PATH), 200)["change_requests"]
    assert (shown["status"], shown["changes"]) == (
        "pending",
        [
            {"field": "start_time", "previous_value": "09:00:00", "requested_value": "10:00:00"},
            {"field": "expected_attendance", "previous_value": 250, "requested_value": 300},
        ],
    )
    assert _event_values(coordinator) == ("09:00:00", 250)

    # --- Approving applies it, in the history as the coordinator's (AC2, AC6) ---
    approved = _body(coordinator.post(_decide_path(raised["id"]), APPROVAL), 200)
    assert (approved["status"], approved["decided_by"], approved["decision_reason"]) == (
        "approved",
        COORDINATOR_ACCOUNT["full_name"],
        APPROVAL["reason"],
    )
    assert _event_values(organiser) == ("10:00:00", 300)
    history = _body(coordinator.get(f"{EVENT_PATH}/history"), 200)["history"]
    applied = []
    for entry in history[-2:]:
        applied.append((entry["kind"], entry["actor_name"], entry["details"]["field"]))
    assert applied == [
        ("field_changed", COORDINATOR_ACCOUNT["full_name"], "start_time"),
        ("field_changed", COORDINATOR_ACCOUNT["full_name"], "expected_attendance"),
    ]
    [on_record] = _body(organiser.get(EVENT_PATH), 200)["change_requests"]
    assert on_record["status"] == "approved"

    # --- The Organiser and the Attendee are told (AC4, AC7) ---
    assert _latest_notification(organiser) == ("change_request_approved", APPROVAL["reason"])
    assert _latest_notification(attendee) == (
        "event_rescheduled",
        f"Partner Summit now runs from {event_day} 10:00 to {event_day} 17:00.",
    )

    # --- It isn't decided twice (AC5) ---
    assert _refusal(coordinator.post(_decide_path(raised["id"]), APPROVAL)) == {
        "error": "change_request_not_pending",
        "message": "Only a pending change request can be decided; this one is approved.",
    }


def test_a_stale_change_is_rejected_and_holds_the_events_decisions_until_then(
    coordinator: Actor,
    organiser: Actor,
    save_event: Callable[[EventRequestStatus], EventRequest],
) -> None:
    save_event(EventRequestStatus.APPROVED)
    raised = _body(organiser.post(CHANGE_REQUESTS_PATH, LATER_AND_BIGGER), 201)

    # --- While it is Pending, the event can't be decided (AC9) ---
    pending = {
        "error": "change_request_pending",
        "message": (
            "The organiser has a change request waiting for your decision. Decide the "
            "change request first."
        ),
    }
    rejection = {"outcome": "rejected", "reason": "The client withdrew."}
    assert _refusal(coordinator.post(f"{EVENT_PATH}/decide", rejection)) == pending
    planning_rejection = {"reason": "The client withdrew."}
    assert _refusal(coordinator.post(f"{EVENT_PATH}/reject", planning_rejection)) == pending

    # --- An edit to a requested field makes it stale; it stays Pending (AC8) ---
    _body(coordinator.patch(EVENT_PATH, {"expected_attendance": 200}), 200)
    assert _refusal(coordinator.post(_decide_path(raised["id"]), APPROVAL)) == {
        "error": "change_request_stale",
        "message": (
            "This change request can't be approved because the event has changed since "
            "it was raised. Expected attendance: 250 when the change was requested, 200 "
            "now. Reject it, and the organiser can raise a new one."
        ),
    }
    [still_pending] = _body(coordinator.get(EVENT_PATH), 200)["change_requests"]
    assert still_pending["status"] == "pending"

    # --- Rejecting needs a reason, and leaves the event as it is (AC3, AC6) ---
    no_reason = coordinator.post(_decide_path(raised["id"]), {"outcome": "rejected"})
    assert _body(no_reason, 400)["details"] == {
        "reason": ["Say why the change request is rejected."]
    }
    rejected = {"outcome": "rejected", "reason": REJECTION_REASON}
    decided = _body(coordinator.post(_decide_path(raised["id"]), rejected), 200)
    assert (decided["status"], decided["decision_reason"]) == ("rejected", REJECTION_REASON)
    assert _event_values(organiser) == ("09:00:00", 200)

    # --- The Organiser is told why (AC4), and the event can be decided again (AC9) ---
    assert _latest_notification(organiser) == ("change_request_rejected", REJECTION_REASON)
    assert _body(coordinator.post(f"{EVENT_PATH}/decide", rejection), 200)["status"] == "rejected"
