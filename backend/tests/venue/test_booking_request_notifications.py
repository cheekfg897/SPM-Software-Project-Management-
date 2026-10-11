"""Unit tests for SCRUM-42 AC9 — Venue Staff are told a request needs a decision.

Every Venue Staff user is notified, once each, after the request is saved (ADR-0015,
ADR-0035). A notification that can't be saved is logged and never fails the request.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import EventRequest
from app.modules.notifications.models import Notification, NotificationKind
from app.modules.notifications.schemas import MESSAGE_BY_KIND
from app.modules.venue import services
from app.modules.venue.models import Venue, VenueBookingRequest
from tests.venue.test_booking_requests import COORDINATOR_ID, _payload

pytestmark = pytest.mark.scrum_42

SavedEvent = Callable[..., EventRequest]


def _raise_request(venue: Venue, event: EventRequest, session: Session) -> VenueBookingRequest:
    return services.raise_booking_request(
        event.id, _payload(venue_id=venue.id), requested_by=COORDINATOR_ID, session=session
    )


def _notifications(session: Session) -> list[Notification]:
    return list(session.scalars(select(Notification).order_by(Notification.recipient_id)))


def test_every_venue_staff_user_is_told_once_with_the_events_reference_and_name(
    db_session: Session,
    saved_users: list[User],
    make_user: Callable[..., User],
    venue: Venue,
    saved_event: SavedEvent,
) -> None:
    db_session.add(make_user(email="staff8@example.com", role=Role.VENUE_STAFF, user_id=8))
    db_session.commit()
    event = saved_event()

    _raise_request(venue, event, db_session)

    notifications = _notifications(db_session)
    assert [
        (n.recipient_id, n.kind, n.event_request_id, n.event_reference, n.event_name)
        for n in notifications
    ] == [
        (staff_id, NotificationKind.VENUE_BOOKING_REQUESTED, event.id, event.reference, event.name)
        for staff_id in (4, 8)
    ]


def test_other_roles_are_not_told(
    db_session: Session, saved_users: list[User], venue: Venue, saved_event: SavedEvent
) -> None:
    _raise_request(venue, saved_event(), db_session)

    assert {n.recipient_id for n in _notifications(db_session)} == {4}


def test_the_message_asks_venue_staff_to_decide() -> None:
    message = MESSAGE_BY_KIND[NotificationKind.VENUE_BOOKING_REQUESTED]

    assert message == "A venue booking request is waiting for your decision."


def test_a_failed_notification_keeps_the_saved_request_and_is_logged(
    db_session: Session,
    saved_users: list[User],
    venue: Venue,
    saved_event: SavedEvent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    event = saved_event()
    failure = OperationalError("INSERT", {}, Exception("database down"))

    with (
        patch.object(services, "notify_users", side_effect=failure),
        caplog.at_level(logging.WARNING, logger="connectsphere.venue"),
    ):
        request = _raise_request(venue, event, db_session)

    db_session.rollback()  # throws away anything that was not committed
    assert db_session.get(VenueBookingRequest, request.id) is not None
    assert _notifications(db_session) == []
    assert [record.getMessage() for record in caplog.records] == [
        f"venue_booking_notification_failed reference={event.reference}"
    ]


def test_a_refused_request_notifies_nobody(
    db_session: Session, saved_users: list[User], venue: Venue, saved_event: SavedEvent
) -> None:
    payload: dict[str, Any] = _payload(venue_id=venue.id, expected_occupancy=150)

    with pytest.raises(ValidationError):
        services.raise_booking_request(
            saved_event().id, payload, requested_by=COORDINATOR_ID, session=db_session
        )

    assert _notifications(db_session) == []
