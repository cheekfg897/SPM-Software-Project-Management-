"""SCRUM-50: the people an arrangement concerns hear about its decisions, via the API.

Two approved events each have a venue booking approved at one hall, back to back. Venue
Staff lengthen the hall's turnaround, which marks both bookings Conflicting, and every
Venue Staff user has a notice for each (AC6). Technical Support then record an equipment
outcome for one event and revise it, and its coordinator has one notice each time, with
the outcome and the note (AC4). Every call goes through the real routes with Flask's
test client (ADR-0031).

The events are saved as approved, with their coordinator; the journey that walks a
request to approval is test_request_to_approval_journey.py.
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

pytestmark = [pytest.mark.scrum_50, pytest.mark.e2e]

PASSWORD = "Password123"
COORDINATOR_ACCOUNT = {"full_name": "Cara Coordinator", "email": "cara@example.com"}
VENUE_STAFF_ACCOUNT = {"full_name": "Vera Venue", "email": "vera@example.com"}
SECOND_VENUE_STAFF_ACCOUNT = {"full_name": "Victor Venue", "email": "victor@example.com"}
TECHNICAL_SUPPORT_ACCOUNT = {"full_name": "Tina Technician", "email": "tina@example.com"}
MORNING_EVENT = "EVR-AAAAAAAA"
LATE_MORNING_EVENT = "EVR-BBBBBBBB"
#: No setup or turnaround, so the two bookings fit back to back until the change.
VENUE = {
    "name": "Main Hall",
    "location": "Level 1",
    "capacity": 300,
    "supported_layouts": ["theatre"],
    "setup_minutes": 0,
    "turnaround_minutes": 0,
}
PROJECTORS = {"name": "Projector", "total_quantity": 10, "store_name": "Central AV store"}
CONFLICTING_DETAIL = (
    "Main Hall: a change to its setup or turnaround time makes this event's booking"
    " overlap another booking or a block."
)


def _body(response: TestResponse, expected_status: int) -> Any:
    """The response's JSON, once its status is the one expected."""
    body = response.get_json()
    assert response.status_code == expected_status, body
    return body


def _notices(actor: Actor, kind: str) -> list[tuple[str, str | None]]:
    """(event reference, detail) of the actor's notices of ``kind``, newest first."""
    notifications = _body(actor.get("/api/notifications"), 200)["notifications"]
    notices = []
    for notification in notifications:
        if notification["kind"] == kind:
            notices.append((notification["event_reference"], notification["detail"]))
    return notices


def _create_staff(account: dict[str, str], role: Role, session: Session) -> int:
    """Create a staff account as staff are created (ADR-0023); return its user id."""
    user = create_staff_user({**account, "password": PASSWORD, "role": role.value}, session=session)
    return user.id


def _staff_actor(account: dict[str, str], role: Role, session: Session, sign_in: SignIn) -> Actor:
    """Create a staff account and sign it in."""
    _create_staff(account, role, session)
    return sign_in(account["email"], PASSWORD)


@pytest.fixture()
def coordinator_id(db_session: Session) -> int:
    """The Event Coordinator's user id; both events are assigned to them."""
    return _create_staff(COORDINATOR_ACCOUNT, Role.EVENT_COORDINATOR, db_session)


@pytest.fixture()
def coordinator(coordinator_id: int, sign_in: SignIn) -> Actor:
    """The Event Coordinator, signed in."""
    return sign_in(COORDINATOR_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def event_day() -> str:
    """The day of both events, a month away, as an ISO date."""
    return (local_today() + timedelta(days=30)).isoformat()


@pytest.fixture()
def approved_events(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    coordinator_id: int,
    event_day: str,
) -> None:
    """Two approved events on the same day, both assigned to the coordinator."""
    for reference in (MORNING_EVENT, LATE_MORNING_EVENT):
        event_request = make_event_request(
            reference=reference,
            status=EventRequestStatus.APPROVED,
            coordinator_id=coordinator_id,
            proposed_date=date.fromisoformat(event_day),
        )
        db_session.add(event_request)
    db_session.commit()


def test_venue_staff_and_the_coordinator_hear_about_what_concerns_them(
    db_session: Session,
    sign_in: SignIn,
    coordinator: Actor,
    approved_events: None,
    event_day: str,
) -> None:
    venue_staff = _staff_actor(VENUE_STAFF_ACCOUNT, Role.VENUE_STAFF, db_session, sign_in)
    second_staff = _staff_actor(SECOND_VENUE_STAFF_ACCOUNT, Role.VENUE_STAFF, db_session, sign_in)
    technical_support = _staff_actor(
        TECHNICAL_SUPPORT_ACCOUNT, Role.TECHNICAL_SUPPORT_STAFF, db_session, sign_in
    )

    # --- Each event's booking at the hall is approved, back to back ---
    venue = _body(venue_staff.post("/api/venues", VENUE), 201)
    periods = {
        MORNING_EVENT: (f"{event_day}T09:00:00+08:00", f"{event_day}T10:00:00+08:00"),
        LATE_MORNING_EVENT: (f"{event_day}T10:30:00+08:00", f"{event_day}T11:30:00+08:00"),
    }
    for reference, (starts_at, ends_at) in periods.items():
        booking = {
            "venue_id": venue["id"],
            "starts_at": starts_at,
            "ends_at": ends_at,
            "purpose": "Partner summit",
        }
        path = f"/api/venues/events/{reference}/booking-requests"
        arrangement = _body(coordinator.post(path, booking), 201)
        decision_path = f"/api/venues/booking-requests/{arrangement['id']}/decision"
        _body(venue_staff.post(decision_path, {"outcome": "approved"}), 200)
    assert _notices(venue_staff, "venue_booking_conflicting") == []

    # --- A longer turnaround makes them overlap: every Venue Staff user hears (AC6) ---
    changed = _body(
        venue_staff.patch(f"/api/venues/{venue['id']}", {"turnaround_minutes": 45}), 200
    )
    assert len(changed["overlap_warnings"]) == 1
    expected = [
        (LATE_MORNING_EVENT, CONFLICTING_DETAIL),
        (MORNING_EVENT, CONFLICTING_DETAIL),
    ]
    assert _notices(venue_staff, "venue_booking_conflicting") == expected
    assert _notices(second_staff, "venue_booking_conflicting") == expected
    assert _notices(coordinator, "venue_booking_conflicting") == []

    # --- Technical Support record an outcome, then revise it (AC4) ---
    projectors = _body(technical_support.post("/api/equipment/types", PROJECTORS), 201)
    line_request = {"equipment_type_id": projectors["id"], "quantity": 4}
    equipment_path = f"/api/events/requests/{MORNING_EVENT}/equipment"
    line = _body(coordinator.post(equipment_path, line_request), 201)
    outcome_path = f"{equipment_path}/{line['id']}/outcome"
    shortfall = {"provided_quantity": 3, "note": "One is being repaired"}
    _body(technical_support.post(outcome_path, shortfall), 200)
    _body(technical_support.post(outcome_path, {"provided_quantity": 4}), 200)

    assert _notices(coordinator, "equipment_outcome_recorded") == [
        (MORNING_EVENT, "Projector: fulfilled, 4 of 4 provided."),
        (
            MORNING_EVENT,
            "Projector: partially fulfilled, 3 of 4 provided. Note: One is being repaired",
        ),
    ]
