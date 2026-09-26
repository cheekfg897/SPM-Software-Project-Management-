"""Service tests for SCRUM-24 "see the events my role is involved in".

AC2: an Event Coordinator sees the submitted requests no coordinator has yet, as a
list separate from their own assigned one (``test_list_assigned_requests.py``). AC4:
Technical Support see every event that has an equipment request, whatever its status
or date. Later commits add AC7 (a coordinator reading an event record).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest

from app.modules.equipment.models import EquipmentType
from app.modules.events.models import EventEquipmentLine, EventRequest, EventRequestStatus
from app.modules.events.services import (
    list_event_requests_with_equipment,
    list_unassigned_event_requests,
)

pytestmark = pytest.mark.scrum_24

MakeEventRequest = Callable[..., EventRequest]
MakeEquipmentLine = Callable[..., EventEquipmentLine]
EventNeeding = Callable[..., EventRequest]
Save = Callable[..., None]

#: Every status but ``submitted``, so a request in it is never mistaken for one
#: still awaiting a coordinator (SCRUM-24 AC2).
STATUSES_OTHER_THAN_SUBMITTED = [
    status for status in EventRequestStatus if status is not EventRequestStatus.SUBMITTED
]


def _references(event_requests: list[EventRequest]) -> list[str]:
    """The listed requests' references, in the order listed."""
    return [event_request.reference for event_request in event_requests]


# --------------------------------------------------------------------------
# AC2 — the submitted requests no coordinator has yet
# --------------------------------------------------------------------------


def test_submitted_requests_with_no_coordinator_are_listed_newest_first(
    save: Save, make_event_request: MakeEventRequest
) -> None:
    save(
        make_event_request(reference="EVR-AAAAAAAA", coordinator_id=None),
        make_event_request(reference="EVR-BBBBBBBB", coordinator_id=3),
        make_event_request(reference="EVR-CCCCCCCC", coordinator_id=None),
    )

    # Saved in one commit, so created_at ties and the later id breaks the tie.
    assert _references(list_unassigned_event_requests()) == ["EVR-CCCCCCCC", "EVR-AAAAAAAA"]


@pytest.mark.parametrize("status", STATUSES_OTHER_THAN_SUBMITTED, ids=lambda status: status.value)
def test_unassigned_requests_in_any_other_status_are_not_listed(
    save: Save, make_event_request: MakeEventRequest, status: EventRequestStatus
) -> None:
    save(make_event_request(status=status, coordinator_id=None))

    assert list_unassigned_event_requests() == []


# --------------------------------------------------------------------------
# AC4 — the events that have an equipment request
# --------------------------------------------------------------------------


def test_events_with_an_equipment_request_are_listed_newest_first(
    event_needing: EventNeeding, save: Save, make_event_request: MakeEventRequest
) -> None:
    event_needing("EVR-AAAAAAAA")
    save(make_event_request(reference="EVR-BBBBBBBB"))
    event_needing("EVR-CCCCCCCC")

    assert _references(list_event_requests_with_equipment()) == ["EVR-CCCCCCCC", "EVR-AAAAAAAA"]


def test_an_event_with_several_lines_is_listed_once(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Save,
) -> None:
    save(make_equipment_line(saved_event_request, equipment_type))
    save(make_equipment_line(saved_event_request, microphone))

    assert _references(list_event_requests_with_equipment()) == ["EVR-AAAAAAAA"]


@pytest.mark.parametrize("status", list(EventRequestStatus), ids=lambda status: status.value)
def test_an_event_with_equipment_is_listed_whatever_its_status(
    event_needing: EventNeeding, status: EventRequestStatus
) -> None:
    event_needing(status=status)

    assert _references(list_event_requests_with_equipment()) == ["EVR-AAAAAAAA"]


def test_an_event_that_has_taken_place_is_still_listed(event_needing: EventNeeding) -> None:
    event_needing(proposed_date=date(2026, 1, 10))

    assert _references(list_event_requests_with_equipment()) == ["EVR-AAAAAAAA"]
