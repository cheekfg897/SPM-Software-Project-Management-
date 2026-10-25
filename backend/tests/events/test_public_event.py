"""Unit tests for the public facts of one event, found by its reference.

SCRUM-24 AC11: an Attendee opens an event they registered for at the address its
notifications link to, which carries the event's reference (SCRUM-28, ADR-0109). The
page shows what SCRUM-52 shows of any event, whatever the event's status now. The
registration module never reads the events table (module boundary), so it asks
``find_public_event``.

Runs against ``db_session`` with the events saved by ``make_open_event``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import PublicEvent, find_public_event

pytestmark = pytest.mark.scrum_24

MakeOpenEvent = Callable[..., EventRequest]

STARTS_AT = datetime(2026, 10, 20, 11, 30, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)
CUT_OFF = STARTS_AT - timedelta(days=1)


def test_an_event_is_found_with_its_public_facts_status_and_cut_off(
    db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    event = make_open_event(cut_off=CUT_OFF)

    found = find_public_event("EVR-OPEN0001", session=db_session)

    assert found == PublicEvent(
        id=event.id,
        reference="EVR-OPEN0001",
        name="Jazz by the Bay",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        status="confirmed",
        withdrawal_cut_off=CUT_OFF,
        description="An evening of music.",
    )


def test_the_reference_may_be_typed_in_any_case_with_spaces_around(
    db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    event = make_open_event()

    found = find_public_event("  evr-open0001 ", session=db_session)

    assert found is not None
    assert found.id == event.id


@pytest.mark.parametrize(
    "status",
    [status for status in EventRequestStatus if status is not EventRequestStatus.DRAFT],
    ids=lambda status: status.value,
)
def test_an_event_is_found_whatever_its_status_but_draft(
    db_session: Session, make_open_event: MakeOpenEvent, status: EventRequestStatus
) -> None:
    make_open_event(status=status)

    found = find_public_event("EVR-OPEN0001", session=db_session)

    assert found is not None
    assert found.status == status.value


def test_a_draft_is_not_found(db_session: Session, make_open_event: MakeOpenEvent) -> None:
    """A draft is its author's alone (SCRUM-20 AC4, ADR-0024)."""
    make_open_event(status=EventRequestStatus.DRAFT)

    assert find_public_event("EVR-OPEN0001", session=db_session) is None


def test_an_unknown_reference_is_not_found(
    db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    make_open_event()

    assert find_public_event("EVR-NOTHERE1", session=db_session) is None


def test_an_event_with_no_description_has_empty_text(
    db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    """The page always shows some text, as the catalogue does (SCRUM-52)."""
    event = make_open_event()
    event.description = None
    db_session.commit()

    found = find_public_event("EVR-OPEN0001", session=db_session)

    assert found is not None
    assert found.description == ""
