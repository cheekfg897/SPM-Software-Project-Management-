"""Unit tests for SCRUM-28 "Receive notifications about my events": a new request.

Covers AC3: when an Event Organiser submits a request, the users it's relevant to are
notified. Until coordinators are assigned (SCRUM-30), that's every Event Coordinator
and nobody else (ADR-0015). Runs against ``db_session`` with the ``saved_users``
fixture, so the coordinators are found by a real query. A failed notification write
doesn't fail the saved request (ADR-0015); that test uses ``mock_session``.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.events.services import submit_event_request
from app.modules.notifications.services import (
    NotificationKind,
    list_notifications_for_recipient,
)

pytestmark = pytest.mark.scrum_28

#: What a notification about the submitted request records, in the order
#: ``_notifications_of`` lists it: event request id, reference, name, kind, read at.
SUBMITTED_NOTIFICATION = (
    1,
    "EVR-AAAAAAAA",
    "ConnectSphere Partner Summit",
    NotificationKind.EVENT_REQUEST_SUBMITTED,
    None,
)


def _submit(payload: dict[str, Any], today: date) -> None:
    """Submit ``payload`` as organiser 7, with a fixed reference."""
    submit_event_request(7, payload, today=today, reference_factory=lambda: "EVR-AAAAAAAA")


def _notifications_of(user_id: int) -> list[tuple[Any, ...]]:
    rows = []
    for notification in list_notifications_for_recipient(user_id):
        rows.append(
            (
                notification.event_request_id,
                notification.event_reference,
                notification.event_name,
                notification.kind,
                notification.read_at,
            )
        )
    return rows


# --------------------------------------------------------------------------
# AC3 — every Event Coordinator hears about a new request, nobody else does
# --------------------------------------------------------------------------


@pytest.mark.parametrize("coordinator_id", [3, 9])
def test_every_event_coordinator_is_notified_of_a_new_request(
    saved_users: list[User],
    valid_event_request_payload: dict[str, Any],
    today: date,
    coordinator_id: int,
) -> None:
    _submit(valid_event_request_payload, today)

    assert _notifications_of(coordinator_id) == [SUBMITTED_NOTIFICATION]


@pytest.mark.parametrize("user_id", [4, 7], ids=["venue-staff", "the-organiser"])
def test_nobody_else_is_notified_of_a_new_request(
    saved_users: list[User],
    valid_event_request_payload: dict[str, Any],
    today: date,
    user_id: int,
) -> None:
    _submit(valid_event_request_payload, today)

    assert _notifications_of(user_id) == []


def test_a_rejected_request_notifies_nobody(
    saved_users: list[User], valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload["proposed_date"] = "2026-09-14"  # yesterday

    with pytest.raises(ValidationError):
        _submit(valid_event_request_payload, today)

    assert _notifications_of(3) == []


# --------------------------------------------------------------------------
# ADR-0015 — a failed notification write doesn't fail the saved request
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("organiser_is_found")
def test_a_failed_notification_write_still_returns_the_saved_request(
    mock_session: MagicMock,
    valid_event_request_payload: dict[str, Any],
    today: date,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The request is committed first; failing its reply would invite a resubmission."""
    mock_session.scalars.return_value = [3]  # one Event Coordinator
    lost_connection = OperationalError("INSERT INTO notifications ...", {}, Exception("gone"))
    mock_session.commit.side_effect = [None, lost_connection]

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        event_request = submit_event_request(
            7,
            valid_event_request_payload,
            session=mock_session,
            today=today,
            reference_factory=lambda: "EVR-AAAAAAAA",
        )

    assert event_request.reference == "EVR-AAAAAAAA"
    assert mock_session.commit.call_count == 2
    mock_session.rollback.assert_called_once()
    assert [record.getMessage() for record in caplog.records] == [
        "event_request_notification_failed reference=EVR-AAAAAAAA"
    ]
