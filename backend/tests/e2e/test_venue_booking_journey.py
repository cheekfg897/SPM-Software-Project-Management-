"""SCRUM-51: a venue booked, a clashing request refused, and equipment reserved.

An Event Coordinator searches for a venue, checks it suits their event and requests it.
A second event asks for the same venue so soon after the first that the venue's setup
and turnaround do not fit between them. Venue Staff approve the first request, which
marks the second Conflicting, and approving the second is refused with a 409 that names
the clash.
Technical Support then reserve the equipment the first event asked for. Every call goes
through the real routes with Flask's test client (ADR-0031); the two events are saved
directly, as the equipment journey saves its events, because getting them approved is
SCRUM-41's journey.

The user stories and acceptance criteria it exercises (SCRUM-51 AC5):

- SCRUM-25 "update venue catalogue": no AC of its own; Venue Staff create the venue the
  journey books, through its route.
- SCRUM-35 "search and filter venues against event requirements": AC1, AC2, AC4. The
  venue is found while it is free, and left out with the no-match message once the
  approval has booked it.
- SCRUM-36 "check whether a venue suits an event": AC1, AC3.
- SCRUM-37 "record what equipment an event needs": AC1.
- SCRUM-42 "request a venue for an event": AC1, AC6 (a new request is Pending).
- SCRUM-43 "approve, hold or reject a venue booking": AC1 (the Venue Staff queue), AC3.
- SCRUM-44 "prevent the same venue being booked twice": AC1, AC2 (the setup and
  turnaround padding), AC4 (the refusal names it), AC5 (the second request is marked
  Conflicting).
- SCRUM-45 "check whether enough equipment is free": AC1.
- SCRUM-46 "reserve equipment": AC1.
- SCRUM-67 "record setup and turnaround time for a venue": AC1, AC3.

A second journey, SCRUM-75's, has a multi-venue event hold one venue tentatively: the
hold shows as Tentative, refuses a clashing approval, and is turned into the confirmed
booking by Venue Staff's final approval.

Each step's banner comment names the ones it covers. It runs with the rest of the suite
in CI, so a broken journey fails the backend check (SCRUM-51 AC4).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time, timedelta
from typing import Any
from urllib.parse import urlencode

import pytest
from sqlalchemy.orm import Session
from werkzeug.test import TestResponse

from app.common.clock import app_timezone, local_today
from app.modules.auth.permissions import Role
from app.modules.auth.services import create_staff_user
from app.modules.events.models import EventRequest, EventRequestStatus
from tests.e2e.actors import Actor, SignIn

pytestmark = [pytest.mark.scrum_51, pytest.mark.e2e]

PASSWORD = "Password123"
COORDINATOR_ACCOUNT = {"full_name": "Cara Coordinator", "email": "cara@example.com"}
VENUE_STAFF_ACCOUNT = {"full_name": "Vic Venue", "email": "vic@example.com"}
TECHNICAL_SUPPORT_ACCOUNT = {"full_name": "Tina Technician", "email": "tina@example.com"}

FIRST_EVENT = "EVR-AAAAAAAA"
SECOND_EVENT = "EVR-BBBBBBBB"

#: Opens 09:00 to 18:00 every day, the default, so both requests fall inside it.
VENUE = {
    "name": "Marina Hall",
    "location": "Marina Bay",
    "capacity": 300,
    "facilities": ["projector"],
    "supported_layouts": ["theatre"],
    "setup_minutes": 30,
    "turnaround_minutes": 30,
}
PROJECTORS = {"name": "Projector", "total_quantity": 10, "store_name": "Central AV store"}
PROJECTORS_NEEDED = 4

#: What each event needs of a venue; the suitability check and the search share it.
REQUIREMENTS = {"required_layout": "theatre", "required_facilities": ["projector"]}
EXPECTED_ATTENDANCE = 250


def _body(response: TestResponse, expected_status: int) -> Any:
    """The response's JSON, once its status is the one expected."""
    body = response.get_json()
    assert response.status_code == expected_status, body
    return body


def _create_staff(account: dict[str, str], role: Role, session: Session) -> int:
    """Create a staff account as staff are created (ADR-0023); return its user id."""
    user = create_staff_user({**account, "password": PASSWORD, "role": role.value}, session=session)
    return user.id


def _on_event_day(event_day: datetime, hour: int, minute: int = 0) -> str:
    """An ISO 8601 moment on the event's day, in business time, as the API takes it."""
    return event_day.replace(hour=hour, minute=minute).isoformat()


def _queue(venue_staff: Actor) -> list[tuple[int, str]]:
    """The id and status of every booking request waiting for Venue Staff."""
    queue = _body(venue_staff.get("/api/venues/booking-requests"), 200)
    return [(row["id"], row["status"]) for row in queue]


@pytest.fixture()
def venue_staff(db_session: Session, sign_in: SignIn) -> Actor:
    """The Venue Staff account, signed in."""
    _create_staff(VENUE_STAFF_ACCOUNT, Role.VENUE_STAFF, db_session)
    return sign_in(VENUE_STAFF_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def technical_support(db_session: Session, sign_in: SignIn) -> Actor:
    """The Technical Support account, signed in."""
    _create_staff(TECHNICAL_SUPPORT_ACCOUNT, Role.TECHNICAL_SUPPORT_STAFF, db_session)
    return sign_in(TECHNICAL_SUPPORT_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def coordinator(db_session: Session, sign_in: SignIn) -> Actor:
    """The Event Coordinator both events are assigned to, signed in."""
    _create_staff(COORDINATOR_ACCOUNT, Role.EVENT_COORDINATOR, db_session)
    return sign_in(COORDINATOR_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def event_day() -> datetime:
    """Midnight, 30 days from today, in business time: both events happen on it."""
    in_thirty_days = local_today() + timedelta(days=30)
    return datetime.combine(in_thirty_days, time(0), tzinfo=app_timezone())


@pytest.fixture()
def two_approved_events(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    coordinator: Actor,
    event_day: datetime,
) -> None:
    """Two approved events on one day, both assigned to the coordinator."""
    coordinator_id = coordinator.get("/api/auth/me").get_json()["id"]
    for reference in (FIRST_EVENT, SECOND_EVENT):
        db_session.add(
            make_event_request(
                reference=reference,
                status=EventRequestStatus.APPROVED,
                coordinator_id=coordinator_id,
                proposed_date=event_day.date(),
            )
        )
    db_session.commit()


def test_a_clashing_venue_request_is_marked_conflicting_and_refused(
    coordinator: Actor,
    venue_staff: Actor,
    technical_support: Actor,
    two_approved_events: None,
    event_day: datetime,
) -> None:
    first_period = {
        "starts_at": _on_event_day(event_day, 9),
        "ends_at": _on_event_day(event_day, 12),
    }
    # 15 minutes after the first ends: inside the 30 + 30 minutes the venue needs.
    second_period = {
        "starts_at": _on_event_day(event_day, 12, 15),
        "ends_at": _on_event_day(event_day, 15),
    }

    # --- 1. Venue Staff set up the venue (SCRUM-67 AC1) ---
    venue = _body(venue_staff.post("/api/venues", VENUE), 201)
    venue_id = venue["id"]
    assert (venue["setup_minutes"], venue["turnaround_minutes"]) == (30, 30)

    # --- 2. Search finds the venue while it is free (SCRUM-35 AC1, AC2) ---
    search = {
        "start_time": first_period["starts_at"],
        "end_time": first_period["ends_at"],
        "min_capacity": EXPECTED_ATTENDANCE,
        **REQUIREMENTS,
    }
    found = _body(coordinator.post("/api/venues/search", search), 200)["results"]
    assert [row["id"] for row in found] == [venue_id]

    # --- 3. The coordinator checks the venue suits the event (SCRUM-36 AC1, AC3) ---
    suitability_path = f"/api/venues/{venue_id}/suitability"
    needs = {"expected_attendance": EXPECTED_ATTENDANCE, **REQUIREMENTS}
    suitable = _body(coordinator.post(suitability_path, needs), 200)
    assert (suitable["suitable"], suitable["reasons"]) == (True, [])

    too_many = {**needs, "expected_attendance": VENUE["capacity"] + 1}
    unsuitable = _body(coordinator.post(suitability_path, too_many), 200)
    assert [reason["requirement"] for reason in unsuitable["reasons"]] == ["capacity"]

    # --- 4. Each event requests the venue, and both wait for a decision ---
    # (SCRUM-42 AC1, AC6; SCRUM-43 AC1). Raising a request marks nothing, so the
    # second one is Pending until the first is approved.
    first_request = _body(
        coordinator.post(
            f"/api/venues/events/{FIRST_EVENT}/booking-requests",
            {"venue_id": venue_id, "purpose": "Main hall", **first_period},
        ),
        201,
    )
    second_request = _body(
        coordinator.post(
            f"/api/venues/events/{SECOND_EVENT}/booking-requests",
            {"venue_id": venue_id, "purpose": "Overflow talks", **second_period},
        ),
        201,
    )
    assert _queue(venue_staff) == [
        (first_request["id"], "pending"),
        (second_request["id"], "pending"),
    ]

    # --- 5. Approving the first marks the second Conflicting ---
    # (SCRUM-43 AC3; SCRUM-44 AC5)
    approved = _body(
        venue_staff.post(
            f"/api/venues/booking-requests/{first_request['id']}/decision",
            {"outcome": "approved"},
        ),
        200,
    )
    assert approved["status"] == "approved"
    assert _queue(venue_staff) == [(second_request["id"], "conflicting")]

    # --- 6. The booking now holds the venue, so search leaves it out ---
    # (SCRUM-35 AC2, AC4; SCRUM-67 AC3: the padding reaches the second period)
    clashing_search = {
        **search,
        "start_time": second_period["starts_at"],
        "end_time": second_period["ends_at"],
    }
    left_out = _body(coordinator.post("/api/venues/search", clashing_search), 200)
    assert left_out == {"results": [], "message": "No venues match your search criteria."}

    # --- 7. Approving the second is refused, naming the clash ---
    # (SCRUM-44 AC1, AC2, AC4: the setup and turnaround are named)
    refused = _body(
        venue_staff.post(
            f"/api/venues/booking-requests/{second_request['id']}/decision",
            {"outcome": "approved"},
        ),
        409,
    )
    clash = refused["details"]
    assert clash["in_buffer"] is True
    assert f"#{clash['booking_id']}" in refused["message"]
    assert "30 minutes of setup and 30 minutes of turnaround" in refused["message"]
    assert clash["occupied_from"] == _on_event_day(event_day, 8, 30)
    assert clash["occupied_until"] == _on_event_day(event_day, 12, 30)
    assert _queue(venue_staff) == [(second_request["id"], "conflicting")]

    # --- 8. Equipment: requested, checked for availability, then reserved ---
    # (SCRUM-37 AC1; SCRUM-45 AC1; SCRUM-46 AC1)
    equipment_type = _body(technical_support.post("/api/equipment/types", PROJECTORS), 201)
    needed = {"equipment_type_id": equipment_type["id"], "quantity": PROJECTORS_NEEDED}
    _body(coordinator.post(f"/api/events/requests/{FIRST_EVENT}/equipment", needed), 201)

    availability_path = f"/api/equipment/events/{FIRST_EVENT}/availability"
    (before,) = _body(technical_support.get(availability_path), 200)
    assert (before["available"], before["requested"], before["shortfall"]) == (10, 4, 0)

    reservation = _body(
        technical_support.post(f"/api/equipment/events/{FIRST_EVENT}/reservations", needed), 201
    )
    assert (reservation["quantity"], reservation["reserved_by"]) == (4, "Tina Technician")
    (after,) = _body(technical_support.get(availability_path), 200)
    assert after["available"] == 6


@pytest.mark.scrum_75
@pytest.mark.scrum_44
def test_a_held_venue_refuses_a_clashing_approval_until_the_hold_is_confirmed(
    coordinator: Actor,
    venue_staff: Actor,
    two_approved_events: None,
    event_day: datetime,
) -> None:
    held_period = {
        "starts_at": _on_event_day(event_day, 9),
        "ends_at": _on_event_day(event_day, 12),
    }
    clashing_period = {
        "starts_at": _on_event_day(event_day, 11),
        "ends_at": _on_event_day(event_day, 14),
    }
    expires_at = (datetime.now(app_timezone()) + timedelta(days=2)).replace(microsecond=0)
    calendar_query = urlencode(
        {"range_start": _on_event_day(event_day, 0), "range_end": _on_event_day(event_day, 23)}
    )

    # --- 1. Venue Staff set up two venues (SCRUM-25 AC3) ---
    hall = _body(venue_staff.post("/api/venues", VENUE), 201)
    side_room = _body(venue_staff.post("/api/venues", {**VENUE, "name": "Side Room"}), 201)
    calendar_path = f"/api/venues/{hall['id']}/calendar?{calendar_query}"

    # --- 2. The first event asks for both venues, so is multi-venue (SCRUM-75) ---
    first_path = f"/api/venues/events/{FIRST_EVENT}/booking-requests"
    hall_request = _body(
        coordinator.post(
            first_path, {"venue_id": hall["id"], "purpose": "Main hall", **held_period}
        ),
        201,
    )
    _body(
        coordinator.post(
            first_path, {"venue_id": side_room["id"], "purpose": "Breakout", **held_period}
        ),
        201,
    )
    clashing_request = _body(
        coordinator.post(
            f"/api/venues/events/{SECOND_EVENT}/booking-requests",
            {"venue_id": hall["id"], "purpose": "Overflow talks", **clashing_period},
        ),
        201,
    )

    # --- 3. Venue Staff hold the hall until an expiry of theirs (SCRUM-75 AC1, AC3) ---
    held = _body(
        venue_staff.post(
            f"/api/venues/booking-requests/{hall_request['id']}/hold",
            {"expires_at": expires_at.isoformat()},
        ),
        200,
    )
    assert (held["status"], held["hold_expires_at"]) == ("on_hold", expires_at.isoformat())

    # --- 4. The hold shows as Tentative, and the coordinator sees it (AC6, AC9) ---
    calendar = _body(venue_staff.get(calendar_path), 200)
    assert [entry["kind"] for entry in calendar] == ["tentative_hold"]
    listed = _body(coordinator.get(first_path), 200)
    assert [(row["status"], row["hold_expires_at"]) for row in listed] == [
        ("on_hold", expires_at.isoformat()),
        ("pending", None),
    ]

    # --- 5. Approving the clashing request is refused, naming the hold (SCRUM-44) ---
    refused = _body(
        venue_staff.post(
            f"/api/venues/booking-requests/{clashing_request['id']}/decision",
            {"outcome": "approved"},
        ),
        409,
    )
    assert refused["details"]["in_buffer"] is False
    assert f"#{refused['details']['booking_id']}" in refused["message"]

    # --- 6. Final approval turns the hold into the confirmed booking (SCRUM-75 AC7) ---
    approved = _body(
        venue_staff.post(
            f"/api/venues/booking-requests/{hall_request['id']}/decision",
            {"outcome": "approved"},
        ),
        200,
    )
    assert (approved["status"], approved["hold_expires_at"]) == ("approved", None)
    calendar = _body(venue_staff.get(calendar_path), 200)
    assert [entry["kind"] for entry in calendar] == ["confirmed_booking"]
