"""Unit tests for SCRUM-93 AC5 — every arrangement on the coordinator's event page.

AC5 (changed 25 Oct): each arrangement has its own status, and all of an event's
arrangements and their statuses are listed on the event record, on the event page
itself; an On Hold arrangement shows its hold expiry there, or that the hold has
expired (Product Owner decision, 25 Oct). The assigned coordinator's record
(``GET /api/events/requests/<reference>``) now lists them as the organiser's and the
staff record do (ADR-0104, ADR-0105).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import CoordinatorEventRecord, get_event_record_for_coordinator
from app.modules.venue.models import BookingRequestStatus, Venue
from tests.conftest import HOLD_STATUSES, place_hold_on
from tests.events.cases import Arrange, SaveArrangement, arrangement_for_record

pytestmark = pytest.mark.scrum_93

REFERENCE = "EVR-AAAAAAAA"
COORDINATOR_ID = 3
HOLD_EXPIRY = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


def test_the_coordinators_record_lists_every_arrangement_with_its_status(
    db_session: Session, saved_users: list[User], arrange: Arrange, save: Callable[..., None]
) -> None:
    """Built from the enum, withdrawn and released ones too; holds keep their expiry."""
    for status in BookingRequestStatus:
        arrangement = arrange(status)
        if status in HOLD_STATUSES:
            place_hold_on(arrangement, HOLD_EXPIRY, save)

    record = get_event_record_for_coordinator(COORDINATOR_ID, REFERENCE, session=db_session)

    shown = [
        (arrangement.status, arrangement.hold_expires_at)
        for arrangement in record.venue_arrangements
    ]
    expected = []
    for status in BookingRequestStatus:
        expected.append((status, HOLD_EXPIRY if status in HOLD_STATUSES else None))
    assert shown == expected


def test_another_events_arrangements_are_left_out(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    make_event_request: Callable[..., EventRequest],
    venue: Venue,
    save: Callable[..., None],
    save_arrangement: SaveArrangement,
) -> None:
    other_event = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=COORDINATOR_ID)
    save(other_event)
    save_arrangement(other_event, venue, BookingRequestStatus.APPROVED)

    record = get_event_record_for_coordinator(COORDINATOR_ID, REFERENCE, session=db_session)

    assert record.venue_arrangements == ()


def test_the_route_sends_the_coordinator_each_arrangement_in_full_and_nothing_else_new(
    call_route: Callable[..., Any],
    replace_services: Callable[..., Any],
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    make_event_request: Callable[..., EventRequest],
) -> None:
    """The planning notes, reservations and safety check stay on their own pages."""
    held = arrangement_for_record(status=BookingRequestStatus.ON_HOLD, hold_expires_at=HOLD_EXPIRY)
    record = CoordinatorEventRecord(
        event_request=make_event_request(status=EventRequestStatus.APPROVED),
        coordinator=None,
        venue_arrangements=(held,),
    )
    replace_services(routes, {"get_event_record_for_coordinator": record})
    coordinator = make_user(role=Role.EVENT_COORDINATOR, user_id=COORDINATOR_ID)

    response, status = call_route(
        "events.get_my_request",
        "GET",
        f"/api/events/requests/{REFERENCE}",
        {"reference": REFERENCE},
        token_for(coordinator),
    )

    assert status == 200
    body = response.get_json()
    [shown] = body["venue_arrangements"]
    assert (shown["status"], shown["hold_expires_at"]) == ("on_hold", "2026-10-30T17:00:00+08:00")
    assert shown["venue_location"] == "Building A"
    organiser_only = {"internal_planning_notes", "equipment_reservations", "safety_outcome"}
    assert organiser_only.isdisjoint(body)
