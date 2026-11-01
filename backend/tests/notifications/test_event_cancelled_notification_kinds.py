"""Unit tests for SCRUM-61 "Cancel an event and release its arrangements": the kinds.

AC1 and AC4: the event's assigned coordinator and every registered Attendee are told the
event was cancelled, with one ``event_cancelled`` kind whose message suits both. AC8:
Venue Staff are told of each booking or hold released, with a kind of their own that
says why, as a rejection's ``venue_booking_released`` does (ADR-0103, ADR-0122).
AC1: the history records the cancellation as an ``event_cancelled`` entry.
"""

from __future__ import annotations

import pytest

from app.modules.events.models import EventHistoryKind
from app.modules.notifications.schemas import MESSAGE_BY_KIND
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_61


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("event_cancelled", "This event has been cancelled by its organiser."),
        (
            "venue_booking_released_by_cancellation",
            "A venue booking or hold was released because its event was cancelled.",
        ),
    ],
    ids=["event", "venue-released"],
)
def test_the_cancellation_notices_say_what_happened(value: str, message: str) -> None:
    kind = NotificationKind(value)

    assert MESSAGE_BY_KIND[kind] == message


def test_the_history_has_an_event_cancelled_kind() -> None:
    assert EventHistoryKind("event_cancelled") is EventHistoryKind.EVENT_CANCELLED
