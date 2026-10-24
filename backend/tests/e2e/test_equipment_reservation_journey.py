"""SCRUM-46: Technical Support reserve equipment for one event, through the API.

Two events share a day. Technical Support reserve projectors for the first, so the
second has fewer free (SCRUM-46 AC2, SCRUM-45 AC1), asking for more than are free is
refused with how many are (AC3), and the event's history shows who reserved what (AC4).
Reserving tells the coordinator nothing by itself (AC5, ADR-0102).
The first event's coordinator reads its equipment but not the other event's, which is
not assigned to them (ADR-0019, ADR-0037). Every call goes through the real routes
with Flask's test client (ADR-0031).

A second journey follows a reservation when units are damaged (SCRUM-47): the free count
drops, the reservation is flagged, its coordinator is told, and returning the units
clears the flag (ADR-0046).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import time, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session
from werkzeug.test import TestResponse

from app.common.clock import local_today
from app.modules.auth.permissions import Role
from app.modules.auth.services import create_staff_user
from app.modules.events.models import EventRequest
from tests.e2e.actors import Actor, SignIn

pytestmark = [pytest.mark.scrum_46, pytest.mark.e2e]

PASSWORD = "Password123"
TECHNICAL_SUPPORT_ACCOUNT = {"full_name": "Tina Technician", "email": "tina@example.com"}
COORDINATOR_ACCOUNT = {"full_name": "Cara Coordinator", "email": "cara@example.com"}
FIRST_EVENT = "EVR-AAAAAAAA"
#: Same day as the first, starting at noon, so the two overlap.
SECOND_EVENT = "EVR-BBBBBBBB"
PROJECTORS = {"name": "Projector", "total_quantity": 10, "store_name": "Central AV store"}


def _body(response: TestResponse, expected_status: int) -> Any:
    """The response's JSON, once its status is the one expected."""
    body = response.get_json()
    assert response.status_code == expected_status, body
    return body


def _free_projectors(actor: Actor, reference: str) -> int:
    """How many of the only equipment type are free for the event."""
    (row,) = _body(actor.get(f"/api/equipment/events/{reference}/availability"), 200)
    return row["available"]


def _latest_notification_kind(actor: Actor) -> str | None:
    """The kind of the actor's newest notification, or ``None`` if they have none."""
    notifications = _body(actor.get("/api/notifications"), 200)["notifications"]
    return notifications[0]["kind"] if notifications else None


def _create_staff(account: dict[str, str], role: Role, session: Session) -> int:
    """Create a staff account as staff are created (ADR-0023); return its user id."""
    user = create_staff_user({**account, "password": PASSWORD, "role": role.value}, session=session)
    return user.id


@pytest.fixture()
def technical_support(db_session: Session, sign_in: SignIn) -> Actor:
    """The Technical Support account, signed in."""
    _create_staff(TECHNICAL_SUPPORT_ACCOUNT, Role.TECHNICAL_SUPPORT_STAFF, db_session)
    return sign_in(TECHNICAL_SUPPORT_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def coordinator_id(db_session: Session) -> int:
    """The Event Coordinator's user id; the first event is assigned to them."""
    return _create_staff(COORDINATOR_ACCOUNT, Role.EVENT_COORDINATOR, db_session)


@pytest.fixture()
def coordinator(coordinator_id: int, sign_in: SignIn) -> Actor:
    """The Event Coordinator, signed in."""
    return sign_in(COORDINATOR_ACCOUNT["email"], PASSWORD)


@pytest.fixture()
def two_overlapping_events(
    db_session: Session, make_event_request: Callable[..., EventRequest], coordinator_id: int
) -> None:
    """The first assigned to the coordinator, the second to nobody yet."""
    db_session.add(make_event_request(reference=FIRST_EVENT, coordinator_id=coordinator_id))
    db_session.add(make_event_request(reference=SECOND_EVENT, start_time=time(12, 0)))
    db_session.commit()


@pytest.fixture()
def upcoming_event(
    db_session: Session, make_event_request: Callable[..., EventRequest], coordinator_id: int
) -> None:
    """An event for the coordinator, still to come (a past one is never flagged)."""
    in_a_month = local_today() + timedelta(days=30)
    db_session.add(
        make_event_request(
            reference=FIRST_EVENT, coordinator_id=coordinator_id, proposed_date=in_a_month
        )
    )
    db_session.commit()


def test_reserving_for_one_event_leaves_less_for_an_overlapping_one(
    technical_support: Actor, coordinator: Actor, two_overlapping_events: None
) -> None:
    equipment_type = _body(technical_support.post("/api/equipment/types", PROJECTORS), 201)
    reservations_path = f"/api/equipment/events/{FIRST_EVENT}/reservations"

    # --- Reserve four for the first event (SCRUM-46 AC1, AC4) ---
    request = {"equipment_type_id": equipment_type["id"], "quantity": 4}
    reservation = _body(technical_support.post(reservations_path, request), 201)
    assert (reservation["quantity"], reservation["reserved_by"]) == (4, "Tina Technician")
    listed = _body(technical_support.get(reservations_path), 200)
    assert [row["id"] for row in listed] == [reservation["id"]]

    # --- The overlapping event has four fewer (SCRUM-46 AC2, SCRUM-45 AC1) ---
    assert _free_projectors(technical_support, SECOND_EVENT) == 6

    # --- One more than is free is refused, naming how many are (SCRUM-46 AC3) ---
    second_path = f"/api/equipment/events/{SECOND_EVENT}/reservations"
    too_many = {"equipment_type_id": equipment_type["id"], "quantity": 7}
    refused = _body(technical_support.post(second_path, too_many), 400)
    assert refused["message"] == "Only 6 available for this period."
    assert _free_projectors(technical_support, SECOND_EVENT) == 6

    # --- The first event's history records who reserved what (SCRUM-46 AC4) ---
    history_path = f"/api/events/requests/{FIRST_EVENT}/history"
    [entry] = _body(technical_support.get(history_path), 200)["history"]
    assert (entry["kind"], entry["actor_name"]) == ("equipment_reserved", "Tina Technician")
    assert entry["details"]["quantity"] == 4

    # --- The first event's coordinator reads its equipment (ADR-0019, ADR-0037) ---
    assert [row["id"] for row in _body(coordinator.get(reservations_path), 200)] == [
        reservation["id"]
    ]
    assert _free_projectors(coordinator, FIRST_EVENT) == 6

    # --- ...but not the second event's, which is not theirs: as if it didn't exist ---
    not_theirs = _body(coordinator.get(f"/api/equipment/events/{SECOND_EVENT}/availability"), 404)
    assert not_theirs["message"] == "Event request not found."


@pytest.mark.scrum_47
def test_damaged_units_flag_the_reservation_until_they_are_returned(
    technical_support: Actor, coordinator: Actor, upcoming_event: None
) -> None:
    equipment_type = _body(technical_support.post("/api/equipment/types", PROJECTORS), 201)
    reservations_path = f"/api/equipment/events/{FIRST_EVENT}/reservations"
    request = {"equipment_type_id": equipment_type["id"], "quantity": 4}
    _body(technical_support.post(reservations_path, request), 201)
    assert [row["needs_attention"] for row in _body(coordinator.get(reservations_path), 200)] == [
        False
    ]
    # Reserving tells the coordinator nothing by itself (SCRUM-46 AC5, ADR-0102).
    assert _latest_notification_kind(coordinator) is None

    # --- Seven of ten are damaged, so three serve four reserved (SCRUM-47 AC1) ---
    out_of_service_path = f"/api/equipment/types/{equipment_type['id']}/out-of-service"
    damaged = {"quantity": 7, "reason": "damaged"}
    entry = _body(technical_support.post(out_of_service_path, damaged), 201)
    assert entry["recorded_by"] == "Tina Technician"

    # --- They no longer count as free for the event (SCRUM-47 AC2) ---
    assert _free_projectors(technical_support, FIRST_EVENT) == 0

    # --- The reservation is flagged, not released; its coordinator is told (AC3) ---
    flagged = _body(coordinator.get(reservations_path), 200)
    assert [row["needs_attention"] for row in flagged] == [True]
    assert flagged[0]["quantity"] == 4
    assert _latest_notification_kind(coordinator) == "significant_change"

    # --- Returning the units puts them back and clears the flag (SCRUM-47 AC1, AC2) ---
    returned = _body(
        technical_support.post(f"/api/equipment/out-of-service/{entry['id']}/return"), 200
    )
    assert returned["resolved_by"] == "Tina Technician"
    assert _body(technical_support.get(out_of_service_path), 200) == []
    assert _free_projectors(technical_support, FIRST_EVENT) == 6
    assert [row["needs_attention"] for row in _body(coordinator.get(reservations_path), 200)] == [
        False
    ]
