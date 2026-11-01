"""SCRUM-61 AC9: an Organiser cancels an event, which frees its venue and equipment.

An approved event has the Main Hall booked by Venue Staff and four projectors reserved
by Technical Support, so another event the same morning finds neither. Its Event
Organiser cancels it with a reason: at once it is Cancelled, the booking is Released
and the hall turns up in a venue search for that period again, and the projectors are
free for the other event. The coordinator is told with the reason and Venue Staff of the
released booking, the organiser sees the cancellation in the history, and cancelling
again is refused. Every call goes through the real routes with Flask's test client
(ADR-0031); the events are saved directly, as the other journeys save theirs, because
getting one approved is SCRUM-41's journey.

The criteria it exercises: SCRUM-61 AC1 (cancelled straight away, the coordinator
notified), AC2 (the booking released, the venue available again), AC3 (the equipment
back in the available quantity), AC8 (Venue Staff told) and AC9. Moved here from
SCRUM-63 (ADR-0122).
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

pytestmark = [pytest.mark.scrum_61, pytest.mark.e2e]

PASSWORD = "Password123"
COORDINATOR_ACCOUNT = {"full_name": "Cara Coordinator", "email": "cara@example.com"}
VENUE_STAFF_ACCOUNT = {"full_name": "Vera Venue", "email": "vera@example.com"}
TECHNICAL_SUPPORT_ACCOUNT = {"full_name": "Tina Technician", "email": "tina@example.com"}
ORGANISER_ACCOUNT = {"full_name": "Olivia Organiser", "email": "olivia@acme.example"}
ORGANISATION = {
    "name": "Acme Events",
    "contact_name": "Olivia Organiser",
    "contact_email": "olivia@acme.example",
}
EVENT = "EVR-AAAAAAAA"
#: Another event the same morning, which wants the same hall and projectors.
OTHER_EVENT = "EVR-BBBBBBBB"
MAIN_HALL = {
    "name": "Main Hall",
    "location": "Level 1",
    "capacity": 300,
    "supported_layouts": ["theatre"],
    "facilities": ["projector"],
}
PROJECTORS = {"name": "Projector", "total_quantity": 10, "store_name": "Central AV store"}
REASON = "Our keynote speaker has withdrawn."
BOOKINGS_PATH = f"/api/venues/events/{EVENT}/booking-requests"
CANCEL_PATH = f"/api/events/requests/{EVENT}/cancel"


def _body(response: TestResponse, expected_status: int) -> Any:
    """The response's JSON, once its status is the one expected."""
    body = response.get_json()
    assert response.status_code == expected_status, body
    return body


def _staff_actor(account: dict[str, str], role: Role, session: Session, sign_in: SignIn) -> Actor:
    """Create a staff account as staff are created (ADR-0023) and sign it in."""
    create_staff_user({**account, "password": PASSWORD, "role": role.value}, session=session)
    return sign_in(account["email"], PASSWORD)


def _latest_notification(actor: Actor) -> tuple[str, str | None]:
    """The kind and detail of the actor's newest notification."""
    newest = _body(actor.get("/api/notifications"), 200)["notifications"][0]
    return newest["kind"], newest["detail"]


def _free_projectors(technical_support: Actor) -> int:
    """How many projectors are free for the other event, the same morning."""
    path = f"/api/equipment/events/{OTHER_EVENT}/availability"
    (row,) = _body(technical_support.get(path), 200)
    return row["available"]


def _venues_free_that_morning(coordinator: Actor, event_day: str) -> list[str]:
    """The names of the venues a search finds free from 09:00 to 12:00 on the day."""
    search = {
        "start_time": f"{event_day}T09:00:00+08:00",
        "end_time": f"{event_day}T12:00:00+08:00",
        "min_capacity": 80,
    }
    found = _body(coordinator.post("/api/venues/search", search), 200)["results"]
    return [venue["name"] for venue in found]


@pytest.fixture()
def coordinator(db_session: Session, sign_in: SignIn) -> Actor:
    return _staff_actor(COORDINATOR_ACCOUNT, Role.EVENT_COORDINATOR, db_session, sign_in)


@pytest.fixture()
def venue_staff(db_session: Session, sign_in: SignIn) -> Actor:
    return _staff_actor(VENUE_STAFF_ACCOUNT, Role.VENUE_STAFF, db_session, sign_in)


@pytest.fixture()
def technical_support(db_session: Session, sign_in: SignIn) -> Actor:
    return _staff_actor(
        TECHNICAL_SUPPORT_ACCOUNT, Role.TECHNICAL_SUPPORT_STAFF, db_session, sign_in
    )


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
def event_day() -> str:
    """The day of both events, a month away, as an ISO date."""
    return (local_today() + timedelta(days=30)).isoformat()


@pytest.fixture()
def approved_event(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    coordinator: Actor,
    organiser: Actor,
    event_day: str,
) -> None:
    """The organiser's approved event, assigned to the coordinator, and another event.

    Both run from 09:00 to 17:00 on ``event_day``.
    """
    coordinator_id = int(_body(coordinator.get("/api/auth/me"), 200)["id"])
    organiser_account = _body(organiser.get("/api/auth/me"), 200)
    day = date.fromisoformat(event_day)
    event = make_event_request(
        reference=EVENT,
        status=EventRequestStatus.APPROVED,
        organiser_id=int(organiser_account["id"]),
        organisation_id=organiser_account["organisation_id"],
        coordinator_id=coordinator_id,
        proposed_date=day,
    )
    other = make_event_request(reference=OTHER_EVENT, proposed_date=day)
    db_session.add_all([event, other])
    db_session.commit()


def test_an_organiser_cancels_and_the_venue_and_equipment_are_free_again(
    coordinator: Actor,
    venue_staff: Actor,
    technical_support: Actor,
    organiser: Actor,
    approved_event: None,
    event_day: str,
) -> None:
    # --- The Main Hall is booked for the event, 09:00 to 12:00 (SCRUM-42, SCRUM-43) ---
    hall = _body(venue_staff.post("/api/venues", MAIN_HALL), 201)
    booking = {
        "venue_id": hall["id"],
        "starts_at": f"{event_day}T09:00:00+08:00",
        "ends_at": f"{event_day}T12:00:00+08:00",
        "purpose": "Keynote",
    }
    arrangement = _body(coordinator.post(BOOKINGS_PATH, booking), 201)
    decision_path = f"/api/venues/booking-requests/{arrangement['id']}/decision"
    _body(venue_staff.post(decision_path, {"outcome": "approved"}), 200)
    assert _venues_free_that_morning(coordinator, event_day) == []

    # --- Four of ten projectors are reserved for it (SCRUM-46) ---
    projectors = _body(technical_support.post("/api/equipment/types", PROJECTORS), 201)
    reservation = {"equipment_type_id": projectors["id"], "quantity": 4}
    _body(technical_support.post(f"/api/equipment/events/{EVENT}/reservations", reservation), 201)
    assert _free_projectors(technical_support) == 6

    # --- The organiser cancels it with a reason, straight away (AC1) ---
    cancelled = _body(organiser.post(CANCEL_PATH, {"reason": REASON}), 200)
    assert (cancelled["reference"], cancelled["status"]) == (EVENT, "cancelled")

    # --- The booking is released and the hall is free that morning again (AC2) ---
    [released] = _body(coordinator.get(BOOKINGS_PATH), 200)
    assert released["status"] == "released"
    assert _venues_free_that_morning(coordinator, event_day) == ["Main Hall"]

    # --- The projectors are back in the available quantity (AC3) ---
    assert _free_projectors(technical_support) == 10

    # --- The coordinator is told why (AC1), and Venue Staff of the booking (AC8) ---
    assert _latest_notification(coordinator) == ("event_cancelled", REASON)
    kind, detail = _latest_notification(venue_staff)
    assert kind == "venue_booking_released_by_cancellation"
    assert detail is not None
    assert detail.startswith(f"Venue arrangement {arrangement['id']} at Main Hall, {event_day}")

    # --- The organiser sees who cancelled it and why in the history ---
    history = _body(organiser.get(f"/api/events/requests/{EVENT}/history"), 200)["history"]
    latest = history[-1]
    assert (latest["kind"], latest["actor_name"], latest["details"]) == (
        "event_cancelled",
        "Olivia Organiser",
        {"reason": REASON},
    )

    # --- Cancelled is final: cancelling again is refused, naming the status ---
    refused = _body(organiser.post(CANCEL_PATH, {"reason": REASON}), 409)
    assert refused["error"] == "cancellation_not_allowed"
    assert refused["message"].endswith("this one is cancelled.")
