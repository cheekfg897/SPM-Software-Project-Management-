"""Unit tests for SCRUM-37 "Record what equipment an event needs": the safety check.

AC4: adding a line, changing a line's quantity or removing a line is a significant
change, and if the event has already passed its Operational Safety Check the approval
is withdrawn and a new check is needed. Changing a line's equipment type counts too;
changing only its technical notes, or sending the values it already has, does not
(ADR-0019). The withdrawal is a ``safety_approval_withdrawn`` history entry by the
coordinator, saved with the line, which ``has_safety_approval`` then reads as no
approval.

A line can change until the event is Confirmed (AC2, ADR-0092). The event here is
mostly Approved, having kept its approval when a flagged venue took it back from
Confirmed (ADR-0053); the usual case, an event in Safety Review that the Safety Officer
has approved, goes back to Approved for a new check (ADR-0087).

The services run against ``db_session``, so ``has_safety_approval`` reads the history
the line change wrote.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.common.errors import ConflictError
from app.modules.auth.models import User
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import (
    EventEquipmentLine,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    add_equipment_line,
    has_safety_approval,
    remove_equipment_line,
    update_equipment_line,
)

pytestmark = pytest.mark.scrum_37

WithdrawalsOf = Callable[[int], list[tuple[int | None, dict[str, Any] | None]]]
ReloadEventRequest = Callable[[int], EventRequest]
MakeEquipmentLine = Callable[..., EventEquipmentLine]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3


@pytest.fixture()
def approved_event(
    saved_users: list[User], approved_for_safety: Callable[[EventRequestStatus], EventRequest]
) -> EventRequest:
    """``saved_event_request``, Approved and with the Safety Officer's approval."""
    return approved_for_safety(EventRequestStatus.APPROVED)


@pytest.fixture()
def projector_line(
    approved_event: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Callable[..., None],
) -> EventEquipmentLine:
    """Two projectors on ``approved_event``, saved after its approval."""
    line = make_equipment_line(approved_event, equipment_type)
    save(line)
    return line


# --------------------------------------------------------------------------
# AC4 — adding, changing or removing a line withdraws the approval
# --------------------------------------------------------------------------


def test_adding_a_line_withdraws_the_safety_approval(
    approved_event: EventRequest, microphone: EquipmentType, safety_withdrawals_of: WithdrawalsOf
) -> None:
    payload = {"equipment_type_id": microphone.id, "quantity": 4}

    add_equipment_line(COORDINATOR_ID, REFERENCE, payload)

    assert has_safety_approval(approved_event.id) is False
    assert safety_withdrawals_of(approved_event.id) == [
        (
            COORDINATOR_ID,
            {"equipment_line_change": "added", "equipment_type_id": microphone.id},
        )
    ]


@pytest.mark.parametrize("change", ["quantity", "equipment_type"])
def test_changing_what_a_line_asks_for_withdraws_the_safety_approval(
    approved_event: EventRequest,
    projector_line: EventEquipmentLine,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    safety_withdrawals_of: WithdrawalsOf,
    change: str,
) -> None:
    """The entry names the type the line asked for before the change."""
    payloads = {"quantity": {"quantity": 3}, "equipment_type": {"equipment_type_id": microphone.id}}

    update_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id, payloads[change])

    assert has_safety_approval(approved_event.id) is False
    assert safety_withdrawals_of(approved_event.id) == [
        (
            COORDINATOR_ID,
            {"equipment_line_change": "changed", "equipment_type_id": equipment_type.id},
        )
    ]


def test_removing_a_line_withdraws_the_safety_approval(
    approved_event: EventRequest,
    projector_line: EventEquipmentLine,
    equipment_type: EquipmentType,
    safety_withdrawals_of: WithdrawalsOf,
) -> None:
    remove_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id)

    assert has_safety_approval(approved_event.id) is False
    assert safety_withdrawals_of(approved_event.id) == [
        (
            COORDINATOR_ID,
            {"equipment_line_change": "removed", "equipment_type_id": equipment_type.id},
        )
    ]


def test_a_line_change_after_the_safety_officer_approved_returns_the_event_to_approved(
    saved_users: list[User],
    approved_for_safety: Callable[[EventRequestStatus], EventRequest],
    microphone: EquipmentType,
    reload_event_request: ReloadEventRequest,
) -> None:
    event = approved_for_safety(EventRequestStatus.SAFETY_REVIEW)
    payload = {"equipment_type_id": microphone.id, "quantity": 4}

    add_equipment_line(COORDINATOR_ID, REFERENCE, payload)

    assert reload_event_request(event.id).status is EventRequestStatus.APPROVED
    assert has_safety_approval(event.id) is False


# --------------------------------------------------------------------------
# AC4 — nothing to withdraw
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [{"notes": "Bring a spare bulb"}, {"quantity": 2}],
    ids=["only-the-notes", "the-same-quantity"],
)
def test_a_line_change_that_asks_for_nothing_new_keeps_the_safety_approval(
    approved_event: EventRequest,
    projector_line: EventEquipmentLine,
    safety_withdrawals_of: WithdrawalsOf,
    payload: dict[str, Any],
) -> None:
    update_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id, payload)

    assert has_safety_approval(approved_event.id) is True
    assert safety_withdrawals_of(approved_event.id) == []


def test_a_refused_duplicate_line_keeps_the_safety_approval(
    approved_event: EventRequest,
    projector_line: EventEquipmentLine,
    equipment_type: EquipmentType,
    safety_withdrawals_of: WithdrawalsOf,
) -> None:
    """The withdrawal is saved with the line, so a line refused takes it back too."""
    payload = {"equipment_type_id": equipment_type.id, "quantity": 1}

    with pytest.raises(ConflictError):
        add_equipment_line(COORDINATOR_ID, REFERENCE, payload)

    assert has_safety_approval(approved_event.id) is True
    assert safety_withdrawals_of(approved_event.id) == []


def test_a_line_added_to_an_event_without_an_approval_withdraws_nothing(
    saved_users: list[User],
    approved_event_request: EventRequest,
    equipment_type: EquipmentType,
    safety_withdrawals_of: WithdrawalsOf,
) -> None:
    payload = {"equipment_type_id": equipment_type.id, "quantity": 1}

    add_equipment_line(COORDINATOR_ID, REFERENCE, payload)

    assert safety_withdrawals_of(approved_event_request.id) == []
