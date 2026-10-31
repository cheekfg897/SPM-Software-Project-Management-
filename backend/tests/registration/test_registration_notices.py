"""Unit tests for SCRUM-62 "Be notified about changes, cancellations and registrations".

AC4: the Event Organiser is told when an Attendee registers or withdraws, since either
changes the places available. AC5: the Attendee is told when their own registration is
confirmed or withdrawn. Only the Organiser who submitted the event and the Attendee
themselves are told (SCRUM-28 AC2, ADR-0125). A refused registration or withdrawal
tells nobody.

Runs against ``db_session``, so the places counted are real SQL.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.modules.events.models import EventRequest
from app.modules.notifications.models import Notification
from app.modules.notifications.services import NotificationKind
from app.modules.registration.models import Registration

pytestmark = pytest.mark.scrum_62

#: The ``register`` and ``withdraw`` fixtures (``tests/registration/conftest.py``).
Act = Callable[[int, int], Registration]

ATTENDEE = 21
OTHER_ATTENDEE = 22
#: ``make_event_request``'s organiser, who submitted every event here.
ORGANISER = 7

CONFIRMED = NotificationKind.REGISTRATION_CONFIRMED
WITHDRAWN = NotificationKind.REGISTRATION_WITHDRAWN
REGISTERED_NOTICE = NotificationKind.ATTENDEE_REGISTERED
WITHDREW_NOTICE = NotificationKind.ATTENDEE_WITHDRAWN


def _notices(session: Session) -> list[tuple[int, int, NotificationKind, str | None]]:
    """Every notice saved, oldest first, as (recipient, event id, kind, detail)."""
    session.rollback()
    rows = []
    for notice in session.scalars(select(Notification).order_by(Notification.id)):
        rows.append((notice.recipient_id, notice.event_request_id, notice.kind, notice.detail))
    return rows


# --------------------------------------------------------------------------
# AC5, AC4 — registering tells the attendee and the organiser
# --------------------------------------------------------------------------


def test_registering_tells_the_attendee_and_the_organiser_the_places_left(
    db_session: Session, register: Act, open_event: EventRequest
) -> None:
    register(ATTENDEE, open_event.id)

    assert _notices(db_session) == [
        (ATTENDEE, open_event.id, CONFIRMED, None),
        (ORGANISER, open_event.id, REGISTERED_NOTICE, "99 of 100 places left."),
    ]


def test_the_notices_name_the_event_and_link_to_it(
    db_session: Session, register: Act, open_event: EventRequest
) -> None:
    """SCRUM-28 AC1: the attendee's link opens their event page (ADR-0109)."""
    register(ATTENDEE, open_event.id)

    db_session.rollback()
    named = [
        (notice.event_reference, notice.event_name)
        for notice in db_session.scalars(select(Notification))
    ]
    assert named == [(open_event.reference, "Jazz by the Bay")] * 2


def test_taking_the_last_place_tells_the_organiser_none_are_left(
    db_session: Session,
    register: Act,
    make_open_event: Callable[..., EventRequest],
) -> None:
    small = make_open_event(capacity=2)
    register(OTHER_ATTENDEE, small.id)

    register(ATTENDEE, small.id)

    assert _notices(db_session)[-1] == (
        ORGANISER,
        small.id,
        REGISTERED_NOTICE,
        "0 of 2 places left.",
    )


def test_registering_again_after_withdrawing_tells_them_again(
    db_session: Session, register: Act, withdraw: Act, open_event: EventRequest
) -> None:
    register(ATTENDEE, open_event.id)
    withdraw(ATTENDEE, open_event.id)

    register(ATTENDEE, open_event.id)

    assert _notices(db_session)[-2:] == [
        (ATTENDEE, open_event.id, CONFIRMED, None),
        (ORGANISER, open_event.id, REGISTERED_NOTICE, "99 of 100 places left."),
    ]


# --------------------------------------------------------------------------
# AC5, AC4 — withdrawing tells the attendee and the organiser
# --------------------------------------------------------------------------


def test_withdrawing_tells_the_attendee_and_the_organiser_the_places_left(
    db_session: Session, register: Act, withdraw: Act, open_event: EventRequest
) -> None:
    register(ATTENDEE, open_event.id)
    register(OTHER_ATTENDEE, open_event.id)

    withdraw(ATTENDEE, open_event.id)

    assert _notices(db_session)[-2:] == [
        (ATTENDEE, open_event.id, WITHDRAWN, None),
        (ORGANISER, open_event.id, WITHDREW_NOTICE, "99 of 100 places left."),
    ]


# --------------------------------------------------------------------------
# A refusal changes no place, so nobody is told
# --------------------------------------------------------------------------


def test_a_refused_registration_tells_nobody(
    db_session: Session, register: Act, open_event: EventRequest
) -> None:
    register(ATTENDEE, open_event.id)
    told_before = _notices(db_session)

    with pytest.raises(AppError):
        register(ATTENDEE, open_event.id)

    assert _notices(db_session) == told_before


def test_a_refused_withdrawal_tells_nobody(
    db_session: Session, withdraw: Act, open_event: EventRequest
) -> None:
    with pytest.raises(AppError):
        withdraw(ATTENDEE, open_event.id)

    assert _notices(db_session) == []
