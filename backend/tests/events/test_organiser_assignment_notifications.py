"""Unit tests for SCRUM-39 "Be notified about review and approval decisions": AC1.

AC1: the Event Organiser who submitted a request is told when an Event Coordinator is
assigned to it, with a ``request_assigned`` notification (ADR-0030). That happens
wherever a coordinator is assigned: a fresh submission, a submitted draft (SCRUM-20)
and a reassignment (SCRUM-87). Only the submitter is told, not their colleagues
(decision 39-1). With no coordinator to assign, nobody is told
(``test_assign_coordinator.py``); a lost notice is covered with the coordinator's
tests, in ``test_submit_event_request_notifies_coordinators.py`` and
``test_reassign_coordinator_notifications.py``.

Runs against ``db_session`` with ``saved_users``: organiser 7 in client organisation
3, and Event Coordinators 3 and 9.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.events.models import EventRequest
from app.modules.events.services import CoordinatorContact, submit_draft_event_request
from app.modules.notifications.schemas import MESSAGE_BY_KIND
from app.modules.notifications.services import NotificationKind
from tests.events.cases import DRAFT_REFERENCE

pytestmark = pytest.mark.scrum_39

SubmitValidRequest = Callable[..., EventRequest]
SaveDraft = Callable[[int, dict[str, Any]], EventRequest]
Reassign = Callable[[int, str], tuple[EventRequest, CoordinatorContact]]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]

ORGANISER_ID = 7
COLLEAGUE_ID = 8


def _organiser_notification(event_request_id: int, reference: str, name: str) -> tuple[Any, ...]:
    """The organiser's assignment notice, as ``notifications_of`` lists it."""
    return (event_request_id, reference, name, NotificationKind.REQUEST_ASSIGNED, None)


# --------------------------------------------------------------------------
# AC1 — the organiser is told a coordinator was assigned
# --------------------------------------------------------------------------


def test_the_organiser_notification_says_a_coordinator_was_assigned() -> None:
    assert (
        MESSAGE_BY_KIND[NotificationKind.REQUEST_ASSIGNED]
        == "An Event Coordinator has been assigned to your event request."
    )


def test_the_organiser_is_told_when_their_submitted_request_is_assigned(
    saved_users: list[User],
    submit_valid_request: SubmitValidRequest,
    notifications_of: NotificationsOf,
) -> None:
    submit_valid_request()

    assert notifications_of(ORGANISER_ID) == [
        _organiser_notification(1, "EVR-AAAAAAAA", "ConnectSphere Partner Summit")
    ]


def test_the_organiser_is_told_when_their_submitted_draft_is_assigned(
    saved_users: list[User],
    save_draft: SaveDraft,
    valid_event_request_payload: dict[str, Any],
    notifications_of: NotificationsOf,
    db_session: Session,
    today: date,
) -> None:
    draft = save_draft(ORGANISER_ID, valid_event_request_payload)

    submit_draft_event_request(ORGANISER_ID, DRAFT_REFERENCE, session=db_session, today=today)

    assert notifications_of(ORGANISER_ID) == [
        _organiser_notification(draft.id, DRAFT_REFERENCE, "ConnectSphere Partner Summit")
    ]


def test_the_organiser_is_told_when_their_request_is_reassigned(
    reassign: Reassign, notifications_of: NotificationsOf, saved_event_request: EventRequest
) -> None:
    reassign(3, "coordinator9@example.com")

    assert notifications_of(ORGANISER_ID) == [
        _organiser_notification(saved_event_request.id, "EVR-AAAAAAAA", "Partner Summit")
    ]


def test_a_colleague_of_the_organiser_is_not_told(
    other_organisers: list[User],
    submit_valid_request: SubmitValidRequest,
    notifications_of: NotificationsOf,
) -> None:
    """A regression guard for decision 39-1: only the submitting organiser is told."""
    submit_valid_request()

    assert notifications_of(COLLEAGUE_ID) == []
