"""Unit tests for SCRUM-43 AC6 — the coordinator is told how their request went.

Only the event's coordinator is told, with the reason as the notification's
``detail``, after the decision is saved (ADR-0015, ADR-0042). SCRUM-115: that is the
coordinator assigned now. If the event was reassigned after the request was raised,
the current coordinator is told (AC1) and the one reassigned away is not (AC2). A
notification that can't be saved is logged and never undoes the decision.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.notifications.models import Notification, NotificationKind
from app.modules.notifications.schemas import MESSAGE_BY_KIND
from app.modules.venue.models import BookingRequestStatus, Venue
from tests.venue.conftest import COORDINATOR_ID, SavedEvent, decide, raise_booking

pytestmark = pytest.mark.scrum_43

DECISION_KINDS = (
    NotificationKind.VENUE_BOOKING_APPROVED,
    NotificationKind.VENUE_BOOKING_REJECTED,
)
#: The other Event Coordinator ``saved_users`` saves, for an event reassigned to them.
OTHER_COORDINATOR_ID = 9


def _decision_notifications(session: Session) -> list[Notification]:
    """The notices about a decision, leaving out the one raising the request sent."""
    return list(
        session.scalars(
            select(Notification)
            .where(Notification.kind.in_(DECISION_KINDS))
            .order_by(Notification.id)
        )
    )


def test_only_the_coordinator_who_raised_the_request_is_told_it_was_approved(
    db_session: Session, saved_users: list[User], venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    request = raise_booking(venue, event, db_session)

    decide(request.id, "approved", db_session)

    notifications = _decision_notifications(db_session)
    assert [(n.recipient_id, n.kind, n.event_reference) for n in notifications] == [
        (COORDINATOR_ID, NotificationKind.VENUE_BOOKING_APPROVED, event.reference)
    ]


@pytest.mark.scrum_115
@pytest.mark.parametrize(
    ("outcome", "kind"),
    [
        ("approved", NotificationKind.VENUE_BOOKING_APPROVED),
        ("rejected", NotificationKind.VENUE_BOOKING_REJECTED),
    ],
)
def test_after_a_reassignment_only_the_current_coordinator_is_told_with_the_reason(
    db_session: Session,
    saved_users: list[User],
    venue: Venue,
    saved_event: SavedEvent,
    outcome: str,
    kind: NotificationKind,
) -> None:
    """AC1 and AC2: the coordinator who raised it was reassigned away, so isn't told."""
    event = saved_event()
    request = raise_booking(venue, event, db_session)
    event.coordinator_id = OTHER_COORDINATOR_ID
    db_session.commit()

    decide(request.id, outcome, db_session, reason="Decided after the reassignment")

    notifications = _decision_notifications(db_session)
    assert [(n.recipient_id, n.kind, n.event_reference, n.detail) for n in notifications] == [
        (OTHER_COORDINATOR_ID, kind, event.reference, "Decided after the reassignment")
    ]


def test_the_rejected_notice_carries_the_reason(
    db_session: Session, saved_users: list[User], venue: Venue, saved_event: SavedEvent
) -> None:
    request = raise_booking(venue, saved_event(), db_session)

    decide(request.id, "rejected", db_session, reason="The hall is closed for repairs")

    notifications = _decision_notifications(db_session)
    assert [(n.kind, n.detail) for n in notifications] == [
        (NotificationKind.VENUE_BOOKING_REJECTED, "The hall is closed for repairs")
    ]


def test_an_approval_without_a_reason_carries_no_detail(
    db_session: Session, saved_users: list[User], venue: Venue, saved_event: SavedEvent
) -> None:
    request = raise_booking(venue, saved_event(), db_session)

    decide(request.id, "approved", db_session)

    assert _decision_notifications(db_session)[0].detail is None


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (NotificationKind.VENUE_BOOKING_APPROVED, "Your venue booking request was approved."),
        (NotificationKind.VENUE_BOOKING_REJECTED, "Your venue booking request was rejected."),
    ],
)
def test_the_message_tells_the_coordinator_the_outcome(
    kind: NotificationKind, expected: str
) -> None:
    assert MESSAGE_BY_KIND[kind] == expected


def test_a_failed_notification_keeps_the_saved_decision_and_is_logged(
    db_session: Session,
    saved_users: list[User],
    venue: Venue,
    saved_event: SavedEvent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The booking is already made; failing the reply would invite a second decision."""
    event = saved_event()
    request = raise_booking(venue, event, db_session)
    real_commit = db_session.commit
    commits: list[str] = []

    def commit_unless_notifying() -> None:
        # The first commit saves the decision and its history; the second is the notice.
        commits.append("commit")
        if len(commits) == 2:
            raise OperationalError("INSERT", {}, Exception("database down"))
        real_commit()

    with (
        patch.object(db_session, "commit", side_effect=commit_unless_notifying),
        caplog.at_level(logging.WARNING, logger="connectsphere.venue"),
    ):
        decide(request.id, "approved", db_session)

    assert _decision_notifications(db_session) == []
    db_session.rollback()  # throws away anything that was not committed
    assert db_session.get(type(request), request.id).status is BookingRequestStatus.APPROVED
    assert [record.getMessage() for record in caplog.records] == [
        f"venue_booking_notification_failed reference={event.reference}"
    ]
