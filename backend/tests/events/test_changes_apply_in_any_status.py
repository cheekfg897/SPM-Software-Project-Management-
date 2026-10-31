"""Unit tests for SCRUM-110 AC6: the status lock is on direct edits only.

Approving a change request (SCRUM-57) applies it in any status where one can be
raised, including before approval. SCRUM-56/57 aren't built yet, so nothing public
applies a change request. These tests call the helpers that apply a change, which
ADR-0116 decision 6 names as the change request's path, on an event whose direct
edit is refused, and check each one still applies it: ``_record_field_changes`` for
the event's fields, and ``_reopen_changed_line`` (through ``_record_line_change``
and ``_clear_outcome``) for a line. A status check added to any of them fails here.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, assigned to Event Coordinator 3, 250 expected).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.modules.events import services as events_services
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from tests.events.cases import AddLine

pytestmark = pytest.mark.scrum_110

HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
ReloadEventRequest = Callable[[int], EventRequest]
ReloadEquipmentLine = Callable[[int], EventEquipmentLine]
SetStatus = Callable[[EventRequestStatus], None]

#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
CHANGED_AT = datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)
#: Statuses in which the coordinator's direct edit, and their line changes, are
#: refused but a change request may still be applied: before approval (SCRUM-110
#: AC2, AC3) and once Confirmed (AC5).
REFUSED_TO_A_DIRECT_EDIT = [
    EventRequestStatus.SUBMITTED,
    EventRequestStatus.UNDER_REVIEW,
    EventRequestStatus.CONFIRMED,
]


@pytest.mark.usefixtures("saved_users")
@pytest.mark.parametrize("status", REFUSED_TO_A_DIRECT_EDIT, ids=lambda status: status.value)
def test_a_field_change_applies_to_an_event_the_direct_edit_refuses(
    db_session: Session,
    saved_event_request: EventRequest,
    set_status: SetStatus,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    events_services._record_field_changes(
        saved_event_request,
        COORDINATOR_ID,
        {"expected_attendance": 300},
        session=db_session,
        now=CHANGED_AT,
    )
    db_session.commit()

    reloaded = reload_event_request(saved_event_request.id)
    assert (reloaded.expected_attendance, reloaded.status) == (300, status)
    assert history_of(saved_event_request.id) == [
        (
            EventHistoryKind.FIELD_CHANGED,
            COORDINATOR_ID,
            {
                "field": "expected_attendance",
                "previous_value": 250,
                "new_value": 300,
                "significant": True,
            },
        )
    ]


@pytest.mark.usefixtures("saved_users")
@pytest.mark.parametrize("status", REFUSED_TO_A_DIRECT_EDIT, ids=lambda status: status.value)
def test_a_line_change_applies_to_an_event_the_direct_edit_refuses(
    db_session: Session,
    saved_event_request: EventRequest,
    add_line: AddLine,
    set_status: SetStatus,
    reload_equipment_line: ReloadEquipmentLine,
    history_of: HistoryOf,
    status: EventRequestStatus,
) -> None:
    line = add_line(2)
    set_status(status)

    events_services._reopen_changed_line(
        COORDINATOR_ID, saved_event_request, line, {"quantity": 5}, db_session
    )
    db_session.commit()

    reopened = reload_equipment_line(line.id)
    assert (reopened.status, reopened.provided_quantity) == (EquipmentLineStatus.REQUESTED, None)
    assert history_of(saved_event_request.id) == [
        (
            EventHistoryKind.FIELD_CHANGED,
            COORDINATOR_ID,
            {
                "field": "equipment_line",
                "previous_value": "Item 0, quantity 2",
                "new_value": "Item 0, quantity 5",
                "significant": True,
            },
        )
    ]
