"""Unit tests for SCRUM-30 AC3: the organiser sees the assigned coordinator.

"The assigned coordinator's name and contact details are visible to the Event
Organiser on the event record." The event record is the organiser's detail view of
one request (``GET /api/events/requests/<reference>``, SCRUM-22). Users record a full
name and an email and nothing else, so those are the contact details; the
coordinator's user id is never shown, and ``coordinator`` is ``null`` until one is
assigned (ADR-0018).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from flask import Flask, Response

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest
from app.modules.events.services import CoordinatorContact, get_event_record_for_organiser

pytestmark = pytest.mark.scrum_30

MakeEventRequest = Callable[..., EventRequest]
SubmitValidRequest = Callable[..., EventRequest]

REFERENCE = "EVR-AAAAAAAA"
COORDINATOR_THREE = CoordinatorContact(
    full_name="Coordinator Three", email="coordinator3@example.com"
)


@pytest.fixture()
def open_record(
    app: Flask,
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    make_event_request: MakeEventRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[CoordinatorContact | None], tuple[Response, int]]:
    """Open the detail route as organiser 7, whose record has the given coordinator."""
    organiser = make_user(role=Role.EVENT_ORGANISER, user_id=7)

    def _open(coordinator: CoordinatorContact | None) -> tuple[Response, int]:
        def fake_get(organiser_id: Any, reference: Any) -> tuple[Any, Any]:
            return make_event_request(reference=REFERENCE, coordinator_id=3), coordinator

        monkeypatch.setattr(routes, "get_event_record_for_organiser", fake_get)
        headers = {"Authorization": f"Bearer {token_for(organiser)}"}
        with app.test_request_context(f"/api/events/requests/{REFERENCE}", headers=headers):
            return routes.get_my_request(reference=REFERENCE)

    return _open


# --------------------------------------------------------------------------
# AC3 — the service finds the coordinator for the organiser's own request
# --------------------------------------------------------------------------


def test_the_organiser_sees_the_assigned_coordinators_name_and_email(
    saved_users: list[User], submit_valid_request: SubmitValidRequest
) -> None:
    submit_valid_request()

    event_request, coordinator = get_event_record_for_organiser("7", REFERENCE)

    assert event_request.reference == REFERENCE
    assert coordinator == COORDINATOR_THREE


def test_an_unassigned_request_shows_no_coordinator(
    saved_users: list[User], save: Callable[..., None], make_event_request: MakeEventRequest
) -> None:
    save(make_event_request(reference=REFERENCE, organiser_id=7, coordinator_id=None))

    event_request, coordinator = get_event_record_for_organiser("7", REFERENCE)

    assert event_request.reference == REFERENCE
    assert coordinator is None


# --------------------------------------------------------------------------
# AC3 — the detail route shows it as ``coordinator``
# --------------------------------------------------------------------------


def test_detail_route_returns_the_request_with_its_coordinators_name_and_email(
    open_record: Callable[[CoordinatorContact | None], tuple[Response, int]],
) -> None:
    response, status = open_record(COORDINATOR_THREE)

    assert status == 200
    body = response.get_json()
    assert body["reference"] == REFERENCE
    assert body["coordinator"] == {
        "full_name": "Coordinator Three",
        "email": "coordinator3@example.com",
    }
    for internal_id in ["id", "organiser_id", "coordinator_id"]:
        assert internal_id not in body


def test_detail_route_shows_null_until_a_coordinator_is_assigned(
    open_record: Callable[[CoordinatorContact | None], tuple[Response, int]],
) -> None:
    response, status = open_record(None)

    assert status == 200
    assert response.get_json()["coordinator"] is None
