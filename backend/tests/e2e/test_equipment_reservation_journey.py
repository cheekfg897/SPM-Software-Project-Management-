"""SCRUM-46: Technical Support reserve equipment for one event, through the API.

Two events share a day. Technical Support reserve projectors for the first, so the
second has fewer free (SCRUM-46 AC2, SCRUM-45 AC1), asking for more than are free is
refused with how many are (AC3), and the event's history shows who reserved what (AC4).
Every call goes through the real routes with Flask's test client (ADR-0031).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import time
from typing import Any

import pytest
from sqlalchemy.orm import Session
from werkzeug.test import TestResponse

from app.modules.auth.permissions import Role
from app.modules.auth.services import create_staff_user
from app.modules.events.models import EventRequest
from tests.e2e.actors import Actor, SignIn

pytestmark = [pytest.mark.scrum_46, pytest.mark.e2e]

TECHNICAL_SUPPORT_ACCOUNT = {"full_name": "Tina Technician", "email": "tina@example.com"}
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


@pytest.fixture()
def technical_support(db_session: Session, sign_in: SignIn) -> Actor:
    """The Technical Support account, created as staff are (ADR-0023) and signed in."""
    password = "Password123"
    create_staff_user(
        {
            **TECHNICAL_SUPPORT_ACCOUNT,
            "password": password,
            "role": Role.TECHNICAL_SUPPORT_STAFF.value,
        },
        session=db_session,
    )
    return sign_in(TECHNICAL_SUPPORT_ACCOUNT["email"], password)


@pytest.fixture()
def two_overlapping_events(
    db_session: Session, make_event_request: Callable[..., EventRequest]
) -> None:
    db_session.add(make_event_request(reference=FIRST_EVENT))
    db_session.add(make_event_request(reference=SECOND_EVENT, start_time=time(12, 0)))
    db_session.commit()


def test_reserving_for_one_event_leaves_less_for_an_overlapping_one(
    technical_support: Actor, two_overlapping_events: None
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
