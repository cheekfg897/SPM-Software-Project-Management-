"""Unit tests for SCRUM-48 — the outcome of an equipment review.

This file covers how an outcome's status follows from the quantity provided, and the
"no outcome yet" seam that SCRUM-97 and SCRUM-49 gate the Safety Review on.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment.models import EquipmentType
from app.modules.events import services
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
)
from app.modules.events.schemas import EquipmentLineWithOutcomeSchema
from app.modules.notifications.models import NotificationKind

pytestmark = pytest.mark.scrum_48


@pytest.mark.parametrize(
    ("quantity", "provided", "expected"),
    [
        (10, 10, EquipmentLineStatus.FULFILLED),
        (10, 6, EquipmentLineStatus.PARTIALLY_FULFILLED),
        (10, 0, EquipmentLineStatus.UNAVAILABLE),
        (1, 1, EquipmentLineStatus.FULFILLED),
    ],
    ids=["all", "some", "none", "single-unit"],
)
def test_the_status_follows_from_how_much_was_provided(
    quantity: int, provided: int, expected: EquipmentLineStatus
) -> None:
    assert services.outcome_status_for(quantity, provided) is expected


def test_a_new_line_has_no_recorded_outcome(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
) -> None:
    line = make_equipment_line(saved_event_request, equipment_type, quantity=10)
    save(line)

    assert line.provided_quantity is None
    assert services.lines_without_outcome(saved_event_request.id, session=db_session) == [line]
    assert services.has_recorded_outcomes(saved_event_request.id, session=db_session) is False


def test_a_line_with_an_outcome_drops_out_of_the_no_outcome_list(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
) -> None:
    """SCRUM-97 gates Safety Review on this list being empty."""
    line = make_equipment_line(saved_event_request, equipment_type, quantity=10)
    save(line)
    line.provided_quantity = 10
    line.status = EquipmentLineStatus.FULFILLED
    db_session.commit()

    assert services.lines_without_outcome(saved_event_request.id, session=db_session) == []
    assert services.has_recorded_outcomes(saved_event_request.id, session=db_session) is True


def test_an_event_with_no_equipment_has_no_lines_awaiting_an_outcome(
    db_session: Session, saved_event_request: EventRequest
) -> None:
    assert services.lines_without_outcome(saved_event_request.id, session=db_session) == []
    # Nothing is outstanding, so "every line has an outcome" holds vacuously.
    assert services.has_recorded_outcomes(saved_event_request.id, session=db_session) is True


def test_the_organiser_never_sees_an_outcome_in_the_history(
    db_session: Session, saved_users: list[User], saved_event_request: EventRequest
) -> None:
    """The outcome is Technical Support's working until a later story shares it."""
    entry = EventHistoryEntry(
        event_request_id=saved_event_request.id,
        kind=EventHistoryKind.EQUIPMENT_OUTCOME_RECORDED,
        actor_id=None,
        details=None,
        occurred_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    db_session.add(entry)
    db_session.commit()

    shown = services.list_event_history(
        saved_event_request.organiser_id,
        saved_event_request.reference,
        viewer_role=Role.EVENT_ORGANISER,
    )

    assert shown == []


# --------------------------------------------------------------------------
# Recording and revising an outcome
# --------------------------------------------------------------------------

REVIEWER_ID = 5
COORDINATOR_ID = 3
RECORDED_AT = datetime(2026, 10, 13, 9, 30, tzinfo=UTC)
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]


@pytest.fixture()
def ten_requested(
    saved_users: list[User],
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
) -> EventEquipmentLine:
    """A line asking for ten units, on an event assigned to coordinator 3."""
    line = make_equipment_line(saved_event_request, equipment_type, quantity=10)
    save(line)
    return line


@pytest.fixture()
def record_outcome(
    db_session: Session, saved_event_request: EventRequest
) -> Callable[..., EventEquipmentLine]:
    """Record an outcome on a line as Technical Support user 5, at a pinned instant."""

    def _record(line: EventEquipmentLine, **payload: Any) -> EventEquipmentLine:
        return services.record_equipment_outcome(
            REVIEWER_ID,
            saved_event_request.reference,
            line.id,
            payload,
            session=db_session,
            now=RECORDED_AT,
        )

    return _record


def _unchanged(db_session: Session, line: EventEquipmentLine) -> bool:
    """Whether the saved line still has no outcome."""
    db_session.expire_all()
    return (line.provided_quantity, line.outcome_note, line.status) == (
        None,
        None,
        EquipmentLineStatus.REQUESTED,
    )


def test_providing_everything_fulfils_the_line_without_a_note(
    record_outcome: Callable[..., EventEquipmentLine], ten_requested: EventEquipmentLine
) -> None:
    line = record_outcome(ten_requested, provided_quantity=10)

    assert line.provided_quantity == 10
    assert line.status is EquipmentLineStatus.FULFILLED
    assert line.outcome_note is None
    assert (line.reviewed_by, line.reviewed_at) == (REVIEWER_ID, RECORDED_AT)


def test_providing_some_is_a_partial_outcome_with_a_shortfall_and_its_note(
    record_outcome: Callable[..., EventEquipmentLine], ten_requested: EventEquipmentLine
) -> None:
    line = record_outcome(ten_requested, provided_quantity=6, note="  Only six in stock  ")

    assert line.status is EquipmentLineStatus.PARTIALLY_FULFILLED
    assert line.quantity - line.provided_quantity == 4
    assert line.outcome_note == "Only six in stock"


def test_providing_none_makes_the_line_unavailable_and_keeps_the_note(
    record_outcome: Callable[..., EventEquipmentLine], ten_requested: EventEquipmentLine
) -> None:
    line = record_outcome(ten_requested, provided_quantity=0, note="All out on loan")

    assert line.status is EquipmentLineStatus.UNAVAILABLE
    assert line.provided_quantity == 0
    assert line.outcome_note == "All out on loan"


@pytest.mark.parametrize("provided", [0, 6], ids=["unavailable", "partial"])
@pytest.mark.parametrize("note", [None, "", "   "], ids=["missing", "empty", "whitespace"])
def test_a_shortfall_needs_a_note_and_leaves_the_line_unchanged(
    db_session: Session,
    record_outcome: Callable[..., EventEquipmentLine],
    ten_requested: EventEquipmentLine,
    provided: int,
    note: str | None,
) -> None:
    payload = {"provided_quantity": provided}
    if note is not None:
        payload["note"] = note

    with pytest.raises(ValidationError) as exc_info:
        record_outcome(ten_requested, **payload)

    assert exc_info.value.details == {"note": [services.OUTCOME_NOTE_REQUIRED_MESSAGE]}
    assert _unchanged(db_session, ten_requested)


def test_providing_more_than_was_requested_is_refused_and_leaves_the_line_unchanged(
    db_session: Session,
    record_outcome: Callable[..., EventEquipmentLine],
    ten_requested: EventEquipmentLine,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        record_outcome(ten_requested, provided_quantity=11, note="Bonus stock")

    assert exc_info.value.details == {
        "provided_quantity": [services.PROVIDED_ABOVE_REQUESTED_MESSAGE]
    }
    assert _unchanged(db_session, ten_requested)


def test_a_negative_quantity_is_refused(
    record_outcome: Callable[..., EventEquipmentLine], ten_requested: EventEquipmentLine
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        record_outcome(ten_requested, provided_quantity=-1, note="Oops")

    assert "provided_quantity" in exc_info.value.details


def test_the_coordinator_is_told_the_outcome_is_recorded(
    record_outcome: Callable[..., EventEquipmentLine],
    ten_requested: EventEquipmentLine,
    saved_event_request: EventRequest,
    notifications_of: Callable[[int], list[tuple[Any, ...]]],
) -> None:
    record_outcome(ten_requested, provided_quantity=10)

    assert notifications_of(COORDINATOR_ID) == [
        (
            saved_event_request.id,
            saved_event_request.reference,
            saved_event_request.name,
            NotificationKind.EQUIPMENT_OUTCOME_RECORDED,
            None,
        )
    ]


def test_an_event_with_no_coordinator_logs_a_warning_and_keeps_the_outcome(
    db_session: Session,
    saved_users: list[User],
    make_event_request: Callable[..., EventRequest],
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    event_request = make_event_request(coordinator_id=None)
    save(event_request)
    line = make_equipment_line(event_request, equipment_type, quantity=10)
    save(line)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        recorded = services.record_equipment_outcome(
            REVIEWER_ID,
            event_request.reference,
            line.id,
            {"provided_quantity": 10},
            session=db_session,
        )

    assert recorded.status is EquipmentLineStatus.FULFILLED
    assert [record.getMessage() for record in caplog.records] == [
        f"event_request_unassigned reference={event_request.reference}"
    ]


def test_recording_writes_one_history_entry_with_the_outcome(
    record_outcome: Callable[..., EventEquipmentLine],
    ten_requested: EventEquipmentLine,
    saved_event_request: EventRequest,
    history_of: HistoryOf,
) -> None:
    record_outcome(ten_requested, provided_quantity=6, note="Only six in stock")

    assert history_of(saved_event_request.id) == [
        (
            EventHistoryKind.EQUIPMENT_OUTCOME_RECORDED,
            REVIEWER_ID,
            {
                "equipment_line_id": ten_requested.id,
                "quantity": 10,
                "provided_quantity": 6,
                "status": "partially_fulfilled",
                "note": "Only six in stock",
            },
        )
    ]


def test_revising_unavailable_to_fulfilled_clears_the_note_and_keeps_both_entries(
    record_outcome: Callable[..., EventEquipmentLine],
    ten_requested: EventEquipmentLine,
    saved_event_request: EventRequest,
    history_of: HistoryOf,
) -> None:
    record_outcome(ten_requested, provided_quantity=0, note="All out on loan")

    line = record_outcome(ten_requested, provided_quantity=10)

    assert (line.status, line.provided_quantity, line.outcome_note) == (
        EquipmentLineStatus.FULFILLED,
        10,
        None,
    )
    assert [details["status"] for _, _, details in history_of(saved_event_request.id)] == [
        "unavailable",
        "fulfilled",
    ]


def test_a_line_of_another_event_is_not_found(
    db_session: Session,
    saved_event_request: EventRequest,
    make_event_request: Callable[..., EventRequest],
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
    ten_requested: EventEquipmentLine,
) -> None:
    other_event = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=3)
    save(other_event)
    other_line = make_equipment_line(other_event, equipment_type, quantity=4)
    save(other_line)

    with pytest.raises(NotFoundError):
        services.record_equipment_outcome(
            REVIEWER_ID,
            saved_event_request.reference,
            other_line.id,
            {"provided_quantity": 4},
            session=db_session,
        )

    assert other_line.provided_quantity is None


def test_a_line_with_an_outcome_leaves_the_awaiting_action_list(
    db_session: Session,
    record_outcome: Callable[..., EventEquipmentLine],
    ten_requested: EventEquipmentLine,
    saved_event_request: EventRequest,
) -> None:
    today = saved_event_request.proposed_date
    before = services.list_equipment_requests_awaiting_action(session=db_session, today=today)
    assert len(before) == 1

    record_outcome(ten_requested, provided_quantity=10)

    after = services.list_equipment_requests_awaiting_action(session=db_session, today=today)
    assert after == []


# --------------------------------------------------------------------------
# Showing the outcome on the event record (AC4)
# --------------------------------------------------------------------------


@pytest.fixture()
def dump_lines(db_session: Session) -> Callable[[list[EventEquipmentLine]], list[dict[str, Any]]]:
    """Serialise lines the way the Technical Support routes show them."""

    def _dump(lines: list[EventEquipmentLine]) -> list[dict[str, Any]]:
        shown = services.equipment_lines_as_shown(lines, session=db_session)
        return EquipmentLineWithOutcomeSchema().dump(shown, many=True)

    return _dump


def test_a_line_shows_its_outcome_and_the_reviewer_by_name(
    record_outcome: Callable[..., EventEquipmentLine],
    dump_lines: Callable[[list[EventEquipmentLine]], list[dict[str, Any]]],
    ten_requested: EventEquipmentLine,
) -> None:
    line = record_outcome(ten_requested, provided_quantity=6, note="Only six in stock")

    [shown] = dump_lines([line])

    assert shown == {
        "id": line.id,
        "equipment_type_id": line.equipment_type_id,
        "quantity": 10,
        "notes": "Needs HDMI",
        "status": "partially_fulfilled",
        "provided_quantity": 6,
        "shortfall": 4,
        "outcome_note": "Only six in stock",
        "reviewed_by": "Alice Example",
        "reviewed_at": "2026-10-13T17:30:00+08:00",
    }


def test_a_line_met_in_full_shows_no_shortfall(
    record_outcome: Callable[..., EventEquipmentLine],
    dump_lines: Callable[[list[EventEquipmentLine]], list[dict[str, Any]]],
    ten_requested: EventEquipmentLine,
) -> None:
    line = record_outcome(ten_requested, provided_quantity=10)

    [shown] = dump_lines([line])

    assert (shown["provided_quantity"], shown["shortfall"], shown["outcome_note"]) == (10, 0, None)


def test_a_line_with_no_outcome_shows_every_outcome_field_empty(
    dump_lines: Callable[[list[EventEquipmentLine]], list[dict[str, Any]]],
    ten_requested: EventEquipmentLine,
) -> None:
    [shown] = dump_lines([ten_requested])

    assert shown["status"] == "requested"
    outcome_fields = [
        "provided_quantity",
        "shortfall",
        "outcome_note",
        "reviewed_by",
        "reviewed_at",
    ]
    assert {name: shown[name] for name in outcome_fields} == dict.fromkeys(outcome_fields)


def test_a_reviewer_who_no_longer_exists_shows_as_none(
    db_session: Session,
    record_outcome: Callable[..., EventEquipmentLine],
    dump_lines: Callable[[list[EventEquipmentLine]], list[dict[str, Any]]],
    saved_users: list[User],
    ten_requested: EventEquipmentLine,
) -> None:
    line = record_outcome(ten_requested, provided_quantity=10)
    reviewer = next(user for user in saved_users if user.id == REVIEWER_ID)
    db_session.delete(reviewer)
    db_session.commit()

    [shown] = dump_lines([line])

    assert shown["reviewed_by"] is None
    assert shown["provided_quantity"] == 10
