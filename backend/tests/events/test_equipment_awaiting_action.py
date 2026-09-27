"""Unit tests for SCRUM-38 "See the equipment requests awaiting my action": the list.

AC1: every equipment request not yet resolved is listed, for events that have not yet
taken place. AC2: each row has the event, the equipment types and quantities still
requested, and the days remaining. AC3: the soonest event comes first. AC4: once
none of an event's lines is still requested, the event drops off. One row per event,
listing only its lines still ``requested``; an event "has not yet taken place" while
its proposed date is today or later, and events that won't run are left out
(ADR-0022). AC5 is in ``test_equipment_awaiting_action_routes.py``.

The service runs against ``db_session``, so the filters and the ordering are real SQL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, time

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.modules.equipment.models import EquipmentType
from app.modules.events import services
from app.modules.events.models import EventEquipmentLine, EventRequest, EventRequestStatus
from app.modules.events.services import (
    EquipmentAwaitingAction,
    list_equipment_requests_awaiting_action,
)

pytestmark = pytest.mark.scrum_38

MakeEventRequest = Callable[..., EventRequest]
MakeEquipmentLine = Callable[..., EventEquipmentLine]
Save = Callable[..., None]
EventNeeding = Callable[..., EventRequest]
SummaryRow = tuple[str, list[tuple[int, int]], int]

REFERENCE = "EVR-AAAAAAAA"


def _summary(awaiting: list[EquipmentAwaitingAction]) -> list[SummaryRow]:
    """Each row as (reference, [(equipment type id, quantity), ...], days remaining)."""
    rows = []
    for row in awaiting:
        lines = []
        for line in row.equipment_lines:
            lines.append((line.equipment_type_id, line.quantity))
        rows.append((row.event_request.reference, lines, row.days_remaining))
    return rows


def _references(awaiting: list[EquipmentAwaitingAction]) -> list[str]:
    """The listed events' references, in the order listed."""
    return [row.event_request.reference for row in awaiting]


def _mark_line_no_longer_requested(session: Session, line_id: int) -> None:
    """Move a line out of ``requested``, as reserving it will (SCRUM-46).

    ``reserved`` doesn't exist yet: SCRUM-46 adds it (ADR-0019). The row is written with
    a plain table update, which the ORM doesn't check against the model's enum, and
    SQLite has no enum type to refuse it. The service leaves such lines out, so the ORM
    never has to load the unknown value.
    """
    lines = EventEquipmentLine.__table__
    session.execute(update(lines).where(lines.c.id == line_id).values(status="reserved"))
    session.commit()


@pytest.fixture()
def two_lines(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Save,
) -> list[EventEquipmentLine]:
    """Four microphones, then two projectors, on REFERENCE (on 2026-10-15).

    Saved in that order, so the microphone line comes first although its equipment
    type was catalogued second.
    """
    microphone_line = make_equipment_line(saved_event_request, microphone, quantity=4)
    save(microphone_line)
    projector_line = make_equipment_line(saved_event_request, equipment_type, quantity=2)
    save(projector_line)
    return [microphone_line, projector_line]


# --------------------------------------------------------------------------
# AC1, AC2 — every unresolved request of an upcoming event, with its lines and days
# --------------------------------------------------------------------------


def test_each_upcoming_event_is_listed_with_its_requested_lines_and_days_remaining(
    two_lines: list[EventEquipmentLine],
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    today: date,
) -> None:
    awaiting = list_equipment_requests_awaiting_action(today=today)

    assert _summary(awaiting) == [(REFERENCE, [(microphone.id, 4), (equipment_type.id, 2)], 30)]


def test_an_event_with_no_equipment_lines_is_not_listed(
    saved_event_request: EventRequest, today: date
) -> None:
    assert list_equipment_requests_awaiting_action(today=today) == []


@pytest.mark.parametrize(
    ("proposed_date", "days_listed"),
    [(date(2026, 9, 14), []), (date(2026, 9, 15), [0]), (date(2026, 9, 16), [1])],
    ids=["yesterday", "today", "tomorrow"],
)
def test_only_events_from_today_on_are_listed(
    event_needing: EventNeeding, today: date, proposed_date: date, days_listed: list[int]
) -> None:
    event_needing(proposed_date=proposed_date)

    awaiting = list_equipment_requests_awaiting_action(today=today)

    assert [row.days_remaining for row in awaiting] == days_listed


@pytest.mark.parametrize(
    "status",
    [
        EventRequestStatus.DRAFT,
        EventRequestStatus.SUBMITTED,
        EventRequestStatus.UNDER_REVIEW,
        EventRequestStatus.AWAITING_CLARIFICATION,
        EventRequestStatus.APPROVED,
        EventRequestStatus.CONFIRMED,
    ],
    ids=lambda status: status.value,
)
def test_events_that_may_still_run_are_listed(
    event_needing: EventNeeding, today: date, status: EventRequestStatus
) -> None:
    # A draft can't hold a line through the service (ADR-0019), but the list's own
    # filter would still show one if it existed (ADR-0022), so it's exercised here
    # the same way AC4 is: written straight into the table.
    event_needing(status=status)

    assert _references(list_equipment_requests_awaiting_action(today=today)) == [REFERENCE]


@pytest.mark.parametrize(
    "status",
    [EventRequestStatus.COMPLETED, EventRequestStatus.CANCELLED, EventRequestStatus.REJECTED],
    ids=lambda status: status.value,
)
def test_events_that_will_not_run_are_not_listed(
    event_needing: EventNeeding, today: date, status: EventRequestStatus
) -> None:
    event_needing(status=status)

    assert list_equipment_requests_awaiting_action(today=today) == []


def test_today_defaults_to_the_business_date(
    monkeypatch: pytest.MonkeyPatch, event_needing: EventNeeding
) -> None:
    monkeypatch.setattr(services, "local_today", lambda: date(2026, 10, 14))
    event_needing(proposed_date=date(2026, 10, 15))

    awaiting = list_equipment_requests_awaiting_action()

    assert [row.days_remaining for row in awaiting] == [1]


# --------------------------------------------------------------------------
# AC3 — ordered by event date, soonest first
# --------------------------------------------------------------------------


def test_events_are_listed_soonest_first(event_needing: EventNeeding, today: date) -> None:
    event_needing("EVR-AAAAAAAA", proposed_date=date(2026, 11, 1))
    event_needing("EVR-BBBBBBBB", proposed_date=date(2026, 9, 20))
    event_needing("EVR-CCCCCCCC", proposed_date=date(2026, 10, 1))

    awaiting = list_equipment_requests_awaiting_action(today=today)

    assert _references(awaiting) == ["EVR-BBBBBBBB", "EVR-CCCCCCCC", "EVR-AAAAAAAA"]


def test_events_on_the_same_day_are_listed_by_start_time_then_as_submitted(
    make_event_request: MakeEventRequest,
    make_equipment_line: MakeEquipmentLine,
    equipment_type: EquipmentType,
    save: Save,
    today: date,
) -> None:
    afternoon = make_event_request(reference="EVR-AAAAAAAA", start_time=time(14, 0))
    save(afternoon)
    first_morning = make_event_request(reference="EVR-BBBBBBBB", start_time=time(9, 0))
    save(first_morning)
    second_morning = make_event_request(reference="EVR-CCCCCCCC", start_time=time(9, 0))
    save(second_morning)
    # Equipment recorded in the opposite order, so the order the lines were added in
    # can't pass for the order the events were submitted in.
    save(make_equipment_line(second_morning, equipment_type))
    save(make_equipment_line(first_morning, equipment_type))
    save(make_equipment_line(afternoon, equipment_type))

    awaiting = list_equipment_requests_awaiting_action(today=today)

    assert _references(awaiting) == ["EVR-BBBBBBBB", "EVR-CCCCCCCC", "EVR-AAAAAAAA"]


# --------------------------------------------------------------------------
# AC4 — fully arranged requests drop off the list
# --------------------------------------------------------------------------


def test_an_event_drops_off_once_none_of_its_lines_is_still_requested(
    db_session: Session, two_lines: list[EventEquipmentLine], today: date
) -> None:
    for line in two_lines:
        _mark_line_no_longer_requested(db_session, line.id)

    assert list_equipment_requests_awaiting_action(today=today) == []


def test_a_partly_arranged_event_shows_only_the_lines_still_requested(
    db_session: Session,
    two_lines: list[EventEquipmentLine],
    equipment_type: EquipmentType,
    today: date,
) -> None:
    microphone_line = two_lines[0]
    _mark_line_no_longer_requested(db_session, microphone_line.id)

    awaiting = list_equipment_requests_awaiting_action(today=today)

    assert _summary(awaiting) == [(REFERENCE, [(equipment_type.id, 2)], 30)]
