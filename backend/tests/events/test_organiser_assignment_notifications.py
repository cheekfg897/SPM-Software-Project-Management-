"""Unit tests for SCRUM-39 "Be notified about review and approval decisions": AC1.

AC1: the Event Organiser who submitted a request is told when an Event Coordinator is
assigned to it, with a ``request_assigned`` notification (ADR-0030).
"""

from __future__ import annotations

import pytest

from app.modules.notifications.schemas import MESSAGE_BY_KIND
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_39


# --------------------------------------------------------------------------
# AC1 — the organiser is told a coordinator was assigned
# --------------------------------------------------------------------------


def test_the_organiser_notification_says_a_coordinator_was_assigned() -> None:
    assert (
        MESSAGE_BY_KIND[NotificationKind.REQUEST_ASSIGNED]
        == "An Event Coordinator has been assigned to your event request."
    )
