"""Unit tests for SCRUM-57 AC7: registered Attendees hear of a new date or time.

When the coordinator approves a change request that changes the event's date or time
(its start or end date or time), every Attendee holding a place is told, with the new
period in business time. An Attendee who withdrew, or who holds a place at another
event, is not; nor is anyone when the approved change is to anything else, or the
change is rejected. The events module asks the registration module who holds a place
(module boundary, ADR-0127).

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, "Partner Summit", organiser 7's, assigned to Event Coordinator 3, on
15 Oct 2026 from 09:00 to 17:00). Attendees 21 and 22 hold places at it; 23 withdrew
from it and 24 holds a place at another event.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any

import pytest

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import EventRequest
from app.modules.events.services import decide_change_request, raise_change_request
from app.modules.notifications.services import (
    NotificationKind,
    list_notifications_for_recipient,
)
from app.modules.registration.models import Registration, RegistrationStatus

pytestmark = pytest.mark.scrum_57

REFERENCE = "EVR-AAAAAAAA"
ORGANISER_ID = 7
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9
HOLDING_PLACES = (21, 22)
WITHDRAWN_ATTENDEE_ID = 23
OTHER_EVENTS_ATTENDEE_ID = 24
TODAY = date(2026, 9, 15)
REASON = "Plans have changed."


@pytest.fixture()
def attendees(
    saved_users: list[User],
    saved_event_request: EventRequest,
    make_user: Callable[..., User],
    make_event_request: Callable[..., EventRequest],
    make_registration: Callable[..., Registration],
    save: Callable[..., None],
) -> None:
    """Attendees 21 and 22 hold places; 23 withdrew; 24 is at ``EVR-BBBBBBBB``."""
    for attendee_id in (*HOLDING_PLACES, WITHDRAWN_ATTENDEE_ID, OTHER_EVENTS_ATTENDEE_ID):
        save(
            make_user(
                email=f"attendee{attendee_id}@example.com",
                role=Role.ATTENDEE,
                user_id=attendee_id,
            )
        )
    other_event = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=COORDINATOR_ID)
    save(other_event)

    for attendee_id in HOLDING_PLACES:
        make_registration(saved_event_request, attendee_id)
    withdrawn = make_registration(saved_event_request, WITHDRAWN_ATTENDEE_ID)
    withdrawn.status = RegistrationStatus.WITHDRAWN
    withdrawn.withdrawn_at = datetime(2026, 9, 14, tzinfo=timezone.utc)
    save(withdrawn)
    make_registration(other_event, OTHER_EVENTS_ATTENDEE_ID)


def _decide(changes: dict[str, Any], decision: dict[str, Any]) -> None:
    """Raise ``changes`` as the Organiser, then decide them as the coordinator."""
    raised = raise_change_request(
        ORGANISER_ID, REFERENCE, {**changes, "reason": REASON}, today=TODAY
    )
    decide_change_request(COORDINATOR_ID, REFERENCE, raised.id, decision, today=TODAY)


def _notices_of(user_id: int) -> list[tuple[str, NotificationKind, str | None]]:
    rows = []
    for notification in list_notifications_for_recipient(user_id):
        rows.append((notification.event_reference, notification.kind, notification.detail))
    return rows


def _rescheduled_notices_of(user_id: int) -> list[tuple[str, NotificationKind, str | None]]:
    rows = []
    for row in _notices_of(user_id):
        if row[1] is NotificationKind.EVENT_RESCHEDULED:
            rows.append(row)
    return rows


@pytest.mark.parametrize(
    ("changes", "new_period"),
    [
        pytest.param(
            {"proposed_date": "2026-10-20"},
            "from 2026-10-20 09:00 to 2026-10-20 17:00",
            id="date",
        ),
        pytest.param(
            {"end_date": "2026-10-16"}, "from 2026-10-15 09:00 to 2026-10-16 17:00", id="end-date"
        ),
        pytest.param(
            {"start_time": "10:00"}, "from 2026-10-15 10:00 to 2026-10-15 17:00", id="start-time"
        ),
        pytest.param(
            {"end_time": "18:30"}, "from 2026-10-15 09:00 to 2026-10-15 18:30", id="end-time"
        ),
    ],
)
def test_every_attendee_holding_a_place_hears_of_a_new_date_or_time(
    attendees: None, changes: dict[str, Any], new_period: str
) -> None:
    _decide(changes, {"outcome": "approved"})

    notice = (
        REFERENCE,
        NotificationKind.EVENT_RESCHEDULED,
        f"Partner Summit now runs {new_period}.",
    )
    for attendee_id in HOLDING_PLACES:
        assert _notices_of(attendee_id) == [notice]


def test_nobody_else_hears_of_the_new_date(attendees: None) -> None:
    """A withdrawn Attendee, another event's, the Organiser and the coordinators."""
    _decide({"proposed_date": "2026-10-20"}, {"outcome": "approved"})

    for user_id in (
        WITHDRAWN_ATTENDEE_ID,
        OTHER_EVENTS_ATTENDEE_ID,
        ORGANISER_ID,
        COORDINATOR_ID,
        OTHER_COORDINATOR_ID,
    ):
        assert _rescheduled_notices_of(user_id) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_attendance": 300},
        {"venue_requirements": "A stage"},
        {"equipment_requirements": "Four projectors"},
        {"programme_notes": "Keynote at ten."},
    ],
    ids=["attendance", "venue-requirements", "equipment-requirements", "programme"],
)
def test_attendees_are_not_told_of_an_approved_change_to_anything_else(
    attendees: None, changes: dict[str, Any]
) -> None:
    _decide(changes, {"outcome": "approved"})

    for attendee_id in HOLDING_PLACES:
        assert _notices_of(attendee_id) == []


def test_attendees_are_not_told_of_a_rejected_change_of_date(attendees: None) -> None:
    _decide({"proposed_date": "2026-10-20"}, {"outcome": "rejected", "reason": "Booked out."})

    for attendee_id in HOLDING_PLACES:
        assert _notices_of(attendee_id) == []


def test_a_new_date_for_an_event_nobody_registered_for_tells_only_the_organiser(
    saved_users: list[User], saved_event_request: EventRequest
) -> None:
    _decide({"proposed_date": "2026-10-20"}, {"outcome": "approved"})

    assert _notices_of(ORGANISER_ID) == [
        (REFERENCE, NotificationKind.CHANGE_REQUEST_APPROVED, None)
    ]
