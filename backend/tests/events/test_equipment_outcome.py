"""Unit tests for SCRUM-48 — the outcome of an equipment review.

This file covers how an outcome's status follows from the quantity provided, and the
"no outcome yet" seam that SCRUM-97 and SCRUM-49 gate the Safety Review on.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

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
