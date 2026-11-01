"""Unit tests for SCRUM-61 AC4: registered Attendees are told their event is cancelled.

Every Attendee still holding a place gets an ``event_cancelled`` notice once the
cancellation is saved, with no ``detail``: the organiser's reason was written for the
coordinator (ADR-0122). An Attendee who withdrew isn't told, and their registrations
are left as they are: the event's status says it is off (ADR-0109). The rest of
the cancellation is in ``test_cancel_event.py``.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, organiser 7, assigned to Event Coordinator 3), confirmed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.events import services as events_services
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import cancel_event_request
from app.modules.notifications.services import NotificationKind
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.registration.services import count_registered
from tests.events.cases import LOST_CONNECTION

pytestmark = pytest.mark.scrum_61

NotificationsOf = Callable[[int], list[tuple[Any, ...]]]
MakeRegistration = Callable[..., Registration]
ReloadEventRequest = Callable[[int], EventRequest]

REFERENCE = "EVR-AAAAAAAA"
COORDINATOR_ID = 3
REASON = "Our keynote speaker has withdrawn."


@pytest.fixture()
def confirmed(
    saved_users: list[User], saved_event_request: EventRequest, save: Callable[..., None]
) -> EventRequest:
    """``saved_event_request`` confirmed, with the users saved."""
    saved_event_request.status = EventRequestStatus.CONFIRMED
    save(saved_event_request)
    return saved_event_request


def _cancel(session: Session) -> EventRequest:
    return cancel_event_request(7, REFERENCE, {"reason": REASON}, session=session)


def test_every_registered_attendee_is_told_without_the_reason(
    db_session: Session,
    confirmed: EventRequest,
    saved_attendees: list[User],
    make_registration: MakeRegistration,
    detailed_notifications_of: NotificationsOf,
) -> None:
    for attendee in saved_attendees:
        make_registration(confirmed, attendee.id)

    _cancel(db_session)

    for attendee in saved_attendees:
        assert detailed_notifications_of(attendee.id) == [
            (REFERENCE, NotificationKind.EVENT_CANCELLED, None)
        ]
    # The coordinator still gets the reason (AC1).
    assert detailed_notifications_of(COORDINATOR_ID) == [
        (REFERENCE, NotificationKind.EVENT_CANCELLED, REASON)
    ]


def test_an_attendee_who_withdrew_is_not_told(
    db_session: Session,
    confirmed: EventRequest,
    saved_attendees: list[User],
    make_registration: MakeRegistration,
    save: Callable[..., None],
    notifications_of: NotificationsOf,
) -> None:
    make_registration(confirmed, 20)
    withdrawn = make_registration(confirmed, 21)
    withdrawn.status = RegistrationStatus.WITHDRAWN
    save(withdrawn)

    _cancel(db_session)

    assert len(notifications_of(20)) == 1
    assert notifications_of(21) == []


def test_registrations_are_left_as_they_were(
    db_session: Session,
    confirmed: EventRequest,
    saved_attendees: list[User],
    make_registration: MakeRegistration,
) -> None:
    """The places aren't withdrawn for them: the event's status says it is off."""
    make_registration(confirmed, 20)

    _cancel(db_session)

    assert count_registered(confirmed.id, session=db_session) == 1


def test_a_lost_attendee_notice_does_not_lose_the_cancellation(
    db_session: Session,
    confirmed: EventRequest,
    saved_attendees: list[User],
    make_registration: MakeRegistration,
    reload_event_request: ReloadEventRequest,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR-0015: the cancellation is saved before anyone is told."""
    make_registration(confirmed, 20)

    def _fail(*_: Any, **__: Any) -> None:
        raise LOST_CONNECTION

    monkeypatch.setattr(events_services, "notify_users", _fail)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        _cancel(db_session)

    assert reload_event_request(confirmed.id).status is EventRequestStatus.CANCELLED
    # One warning for the coordinator's notice and one for the Attendees'.
    assert [record.getMessage() for record in caplog.records] == [
        f"event_request_notification_failed reference={REFERENCE} kind=event_cancelled",
        f"event_request_notification_failed reference={REFERENCE} kind=event_cancelled",
    ]
