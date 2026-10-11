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
from app.modules.events.models import EventHistoryEntry, EventHistoryKind
from app.modules.notifications.models import Notification, NotificationKind
from app.modules.notifications.schemas import MESSAGE_BY_KIND
from app.modules.venue import services
from app.modules.venue.models import Venue, VenueBookingRequest
from tests.venue.conftest import COORDINATOR_ID, SavedEvent, booking_payload, raise_booking

pytestmark = pytest.mark.scrum_42


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

    raise_booking(venue, event, db_session)

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
    raise_booking(venue, saved_event(), db_session)

    assert {n.recipient_id for n in _notifications(db_session)} == {4}


def test_the_message_asks_venue_staff_to_decide() -> None:
    message = MESSAGE_BY_KIND[NotificationKind.VENUE_BOOKING_REQUESTED]

    assert message == "A venue booking request is waiting for your decision."


def test_a_failed_notification_keeps_the_saved_request_and_its_history_and_is_logged(
    db_session: Session,
    saved_users: list[User],
    venue: Venue,
    saved_event: SavedEvent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    event = saved_event()
    real_commit = db_session.commit
    commits: list[str] = []

    def commit_unless_notifying() -> None:
        # The first commit saves the request and its history; the second is the staff's.
        commits.append("commit")
        if len(commits) == 2:
            raise OperationalError("INSERT", {}, Exception("database down"))
        real_commit()

    with (
        patch.object(db_session, "commit", side_effect=commit_unless_notifying),
        caplog.at_level(logging.WARNING, logger="connectsphere.venue"),
    ):
        request = raise_booking(venue, event, db_session)

    # The half-written notifications were rolled back, not left waiting in the session.
    assert _notifications(db_session) == []
    db_session.rollback()  # throws away anything that was not committed
    assert db_session.get(VenueBookingRequest, request.id) is not None
    assert [entry.kind for entry in db_session.scalars(select(EventHistoryEntry))] == [
        EventHistoryKind.VENUE_BOOKING_REQUESTED
    ]
    assert [record.getMessage() for record in caplog.records] == [
        f"venue_booking_notification_failed reference={event.reference}"
    ]


def test_a_refused_request_notifies_nobody(
    db_session: Session, saved_users: list[User], venue: Venue, saved_event: SavedEvent
) -> None:
    payload: dict[str, Any] = booking_payload(venue_id=venue.id, expected_occupancy=150)

    with pytest.raises(ValidationError):
        services.raise_booking_request(
            saved_event().id, payload, requested_by=COORDINATOR_ID, session=db_session
        )

    assert _notifications(db_session) == []
