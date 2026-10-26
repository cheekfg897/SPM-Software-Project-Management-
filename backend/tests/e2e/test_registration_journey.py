"""SCRUM-63: attendees fill an event; one withdraws and registers again, via the API.

This is SCRUM-63's registration journey (and SCRUM-53's before it). It exercises these
user stories and acceptance criteria (SCRUM-63 AC5):

- SCRUM-63 AC1: registration up to capacity, a refusal at capacity, a withdrawal and a
  successful re-registration.
- SCRUM-69 AC1, AC2, AC4: the coordinator opens registration with a capacity, which is
  refused until the event is confirmed.
- SCRUM-42 and SCRUM-43: a venue is booked and Venue Staff approve it.
- SCRUM-97 AC1, AC2 and SCRUM-98 AC1: the event, which has no equipment, goes to Safety
  Review and the Safety Officer approves it.
- SCRUM-49 AC1, AC2: the coordinator confirms the event.
- SCRUM-52 AC1, AC2, AC5: the event is in the catalogue; attendees register with their
  account and see the event in their list.
- SCRUM-54 AC1, AC2, AC3: the event fills and is shown full, a further registration is
  refused, and a withdrawal frees a place that a further registration takes.
- SCRUM-53 AC1, AC2, AC5: attendees see each registration's status, withdraw, and the
  place goes back to the event's capacity.
- SCRUM-55 AC2, AC3, AC4: the coordinator's list of registrants shows each status and
  the count against the capacity.

The journey. The event starts out approved, so the coordinator can't open
registration yet. A venue is booked and approved, the Safety Officer approves the event,
and the coordinator confirms it: the event reaches Confirmed through the real routes
rather than being saved that way. The coordinator opens registration with two places.
Alice and Bob fill them, the catalogue shows the event full with no places left, and
Carol is turned away. Alice withdraws and Carol takes the freed place, so Alice,
registering again, is turned away too: a withdrawn attendee has no claim on the place.
Bob withdraws, and Alice registers again into his place, on her own registration once
more (ADR-0032). Dan holds a place at a second confirmed event the whole time: it never
counts against this event's places, and that event loses only his. Every call goes
through the real routes with Flask's test client (ADR-0031).

SCRUM-63 AC2 (a confirmed event's date change flagging its bookings, through to Venue
Staff reconfirming) and AC3 (a cancellation releasing them) are deferred until SCRUM-56
to SCRUM-61 land; none of them is built yet. AC4 is met by CI's backend job, which runs
every test under ``tests/`` with no marker filter, this one included; main's ruleset
requires every CI check to pass before a merge (Product Owner, 20 Oct).

Defaults settled in SCRUM-63's question pass:

1. The journey runs through Flask's test client on the in-memory database, as ADR-0031
   and SCRUM-51's journeys do, marked ``scrum_63`` and ``e2e``.
2. SCRUM-53's registration journey is extended rather than copied.
3. "Up to capacity" is a capacity of two: two attendees fill it and a third is refused.
4. "A successful re-registration" is the attendee who withdrew registering again into a
   freed place, which reuses her registration (ADR-0032).
5. The event reaches Confirmed through the real routes. It is saved as approved, with
   its coordinator; the request-to-approval journey is
   test_request_to_approval_journey.py. The second event is only a decoy for the
   counts, so it is saved as confirmed with registration open.

The Event Organiser's own view of the registrants is not walked here: their account
would have to be linked to the event's client organisation first, which
test_request_to_approval_journey.py does. The coordinator reads the same list.
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

pytestmark = [pytest.mark.scrum_53, pytest.mark.scrum_63, pytest.mark.e2e]

PASSWORD = "Password123"
COORDINATOR_ACCOUNT = {"full_name": "Cara Coordinator", "email": "cara@example.com"}
VENUE_STAFF_ACCOUNT = {"full_name": "Vera Venue", "email": "vera@example.com"}
SAFETY_OFFICER_ACCOUNT = {"full_name": "Sam Safety", "email": "sam@example.com"}
EVENT = "EVR-AAAAAAAA"
DECOY_EVENT = "EVR-BBBBBBBB"
DECOY_PLACES = 5
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
TWO_PLACES = {"registration_enabled": True, "registration_capacity": 2}
SETTINGS_PATH = f"/api/events/requests/{EVENT}/registration"
EVENT_FULL = {"error": "event_full", "message": "This event is full."}


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


def _refusal(response: TestResponse) -> dict[str, str]:
    """A 409's error code and message."""
    body = _body(response, 409)
    return {"error": body["error"], "message": body["message"]}


def _places(client: FlaskClient, event_id: int) -> tuple[int, bool]:
    """The event's places left and whether it is full, as the public catalogue shows."""
    listed = _body(client.get("/api/events/catalogue"), 200)["items"]
    for entry in listed:
        if entry["id"] == event_id:
            return entry["places_left"], entry["is_full"]
    raise AssertionError(f"event {event_id} is not in the catalogue")


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
    """The Event Coordinator's user id; both events are assigned to them."""
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


@pytest.fixture()
def decoy_event(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    coordinator_id: int,
    event_day: str,
) -> int:
    """Another confirmed event with registration open for five; returns its id."""
    event_request = make_event_request(
        reference=DECOY_EVENT,
        status=EventRequestStatus.CONFIRMED,
        coordinator_id=coordinator_id,
        proposed_date=date.fromisoformat(event_day),
    )
    event_request.registration_enabled = True
    event_request.registration_capacity = DECOY_PLACES
    db_session.add(event_request)
    db_session.commit()
    return event_request.id


def test_attendees_fill_an_event_and_one_who_withdrew_registers_again(
    client: FlaskClient,
    sign_in: SignIn,
    coordinator: Actor,
    venue_staff: Actor,
    safety_officer: Actor,
    approved_event: int,
    decoy_event: int,
    event_day: str,
) -> None:
    registrations_path = f"/api/events/catalogue/{approved_event}/registrations"
    alice = _attendee("Alice", client, sign_in)
    bob = _attendee("Bob", client, sign_in)
    carol = _attendee("Carol", client, sign_in)
    dan = _attendee("Dan", client, sign_in)

    # --- Dan holds a place at the decoy, which never counts against this event ---
    decoy_path = f"/api/events/catalogue/{decoy_event}/registrations"
    assert _body(dan.post(decoy_path), 201)["status"] == "registered"

    # --- Registration can't open before the event is confirmed (SCRUM-69 AC4) ---
    assert _refusal(coordinator.patch(SETTINGS_PATH, TWO_PLACES)) == {
        "error": "registration_not_enablable",
        "message": "Registration can be enabled only for a confirmed event.",
    }

    # --- A venue is booked and approved, and the event passes its safety check
    # --- (SCRUM-42, SCRUM-43, SCRUM-97 AC1, AC2, SCRUM-98 AC1) ---
    _book_the_hall(coordinator, venue_staff, event_day)
    _pass_safety_check(coordinator, safety_officer)

    # --- The coordinator confirms it (SCRUM-49 AC1, AC2) ---
    confirmed = _body(coordinator.post(f"/api/events/requests/{EVENT}/confirm"), 200)
    assert confirmed["status"] == "confirmed"

    # --- The coordinator opens registration with two places (SCRUM-69 AC1, AC2) ---
    settings = _body(coordinator.patch(SETTINGS_PATH, TWO_PLACES), 200)
    assert (settings["registration_enabled"], settings["registration_capacity"]) == (True, 2)
    assert _places(client, approved_event) == (2, False)

    # --- Alice and Bob register, and each sees it in their list (SCRUM-52 AC2, AC5) ---
    first_registration = _body(alice.post(registrations_path), 201)
    assert first_registration["status"] == "registered"
    assert _my_registration_statuses(alice) == ["registered"]
    assert _places(client, approved_event) == (1, False)
    assert _body(bob.post(registrations_path), 201)["status"] == "registered"
    assert _my_registration_statuses(bob) == ["registered"]

    # --- Up to capacity: the catalogue shows it full (SCRUM-63 AC1, SCRUM-54 AC1) ---
    assert _places(client, approved_event) == (0, True)

    # --- Carol is turned away at capacity (SCRUM-63 AC1, SCRUM-54 AC2) ---
    assert _refusal(carol.post(registrations_path)) == EVENT_FULL
    assert _my_registration_statuses(carol) == []
    assert _places(client, approved_event) == (0, True)

    # --- Alice withdraws; the row stays, and the place is free (SCRUM-63 AC1,
    # --- SCRUM-53 AC1, AC2, AC5) ---
    withdrawn = _body(alice.delete(registrations_path), 200)
    assert withdrawn["status"] == "withdrawn"
    assert _my_registration_statuses(alice) == ["withdrawn"]
    assert _places(client, approved_event) == (1, False)

    # --- Carol takes the freed place (SCRUM-54 AC3) ---
    assert _body(carol.post(registrations_path), 201)["status"] == "registered"
    assert _my_registration_statuses(carol) == ["registered"]
    assert _places(client, approved_event) == (0, True)

    # --- Alice, registering again, is turned away: the place is gone (ADR-0032) ---
    assert _refusal(alice.post(registrations_path)) == EVENT_FULL
    assert _my_registration_statuses(alice) == ["withdrawn"]

    # --- Bob withdraws, and Alice registers again into his place (SCRUM-63 AC1,
    # --- SCRUM-54 AC3, ADR-0032) ---
    assert _body(bob.delete(registrations_path), 200)["status"] == "withdrawn"
    assert _places(client, approved_event) == (1, False)
    registered_again = _body(alice.post(registrations_path), 201)
    assert registered_again["status"] == "registered"
    assert registered_again["id"] == first_registration["id"]
    assert _my_registration_statuses(alice) == ["registered"]
    assert _places(client, approved_event) == (0, True)

    # --- The coordinator's list of registrants shows each one's status (SCRUM-55 AC2,
    # --- AC3, AC4) ---
    registrants = _body(coordinator.get(f"/api/events/requests/{EVENT}/registrations"), 200)
    assert (
        registrants["capacity"],
        registrants["registered_count"],
        registrants["places_left"],
    ) == (2, 2, 0)
    statuses = {row["name"]: row["status"] for row in registrants["items"]}
    assert statuses == {"Alice": "registered", "Bob": "withdrawn", "Carol": "registered"}

    # --- The decoy has lost only Dan's place ---
    assert _places(client, decoy_event) == (DECOY_PLACES - 1, False)
