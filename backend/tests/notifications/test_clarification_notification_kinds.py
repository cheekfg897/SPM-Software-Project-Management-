"""Unit tests for SCRUM-32 "Ask the Organiser for clarification": notification kinds.

AC1: the organiser is told when the coordinator asks for clarification. AC2: the
coordinator is told when the organiser answers. Each has its own kind and message;
the question or the answer itself is the notification's detail (ADR-0029).
"""

from __future__ import annotations

import pytest

from app.modules.notifications.schemas import MESSAGE_BY_KIND
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_32


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (
            "clarification_requested",
            "Your Event Coordinator has asked for clarification on your event request.",
        ),
        (
            "clarification_answered",
            "The organiser has answered your request for clarification.",
        ),
    ],
    ids=["requested", "answered"],
)
def test_the_clarification_notifications_say_what_happened(value: str, message: str) -> None:
    kind = NotificationKind(value)

    assert MESSAGE_BY_KIND[kind] == message
