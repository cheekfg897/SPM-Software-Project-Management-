"""Unit tests for SCRUM-22 "Define the event status model".

AC1: an event request holds exactly one of the story's seven statuses, and each one
survives a trip through the database. AC2: the status is shown by its value. The
choices behind the list (``under_review`` for "Under Review / Planning", no
``approved``) are in ADR-0012.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.schemas import EventRequestSchema

pytestmark = pytest.mark.scrum_22

MakeEventRequest = Callable[..., EventRequest]


def _saved(db_session: Session, event_request: EventRequest) -> EventRequest:
    db_session.add(event_request)
    db_session.commit()
    return event_request


# --------------------------------------------------------------------------
# AC1 — exactly one of the seven statuses
# --------------------------------------------------------------------------


def test_status_values_are_exactly_the_seven_in_the_story() -> None:
    values = [status.value for status in EventRequestStatus]

    assert values == [
        "draft",
        "submitted",
        "under_review",
        "confirmed",
        "completed",
        "cancelled",
        "rejected",
    ]


@pytest.mark.parametrize("status", list(EventRequestStatus), ids=lambda status: status.value)
def test_every_status_round_trips_through_the_status_column(
    db_session: Session, make_event_request: MakeEventRequest, status: EventRequestStatus
) -> None:
    saved = _saved(db_session, make_event_request(status=status))
    db_session.expire_all()

    reloaded = db_session.get(EventRequest, saved.id)
    stored = db_session.execute(text("SELECT status FROM event_requests")).scalar_one()

    assert reloaded is not None
    assert reloaded.status is status
    assert stored == status.value


# --------------------------------------------------------------------------
# AC2 — the status is shown by its value
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", list(EventRequestStatus), ids=lambda status: status.value)
def test_every_status_is_shown_by_its_value(
    make_event_request: MakeEventRequest, status: EventRequestStatus
) -> None:
    dumped = EventRequestSchema().dump(make_event_request(status=status))

    assert dumped["status"] == status.value
