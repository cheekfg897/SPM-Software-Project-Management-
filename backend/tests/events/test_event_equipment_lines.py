"""Unit tests for SCRUM-37 "Record what equipment an event needs": the equipment lines.

AC1: an Event Coordinator adds one or more lines to an event, each with an equipment
type, a quantity and technical notes. AC2: a line can be edited or removed while the
request is still awaiting review (``submitted`` or ``under_review``). AC3: a quantity
of zero or less is refused. AC4: the lines and their current state are visible on the
event record. One line per equipment type per event, and the database holds the same
rules as the schema (ADR-0019). Only the event's assigned coordinator (SCRUM-30) adds,
edits, removes or lists its lines; any other coordinator, or anyone on an unassigned
event, gets the same 404 as an unknown event. Technical Support Staff list any event's
lines. AC5 is in ``test_event_equipment_notifications.py``.

The services run against ``db_session``, so the lookups and orderings are real SQL.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.schemas import EquipmentLineSchema, EventRequestDetailSchema
from app.modules.events.services import (
    DUPLICATE_LINE_MESSAGE,
    NOT_AWAITING_REVIEW_MESSAGE,
    RequestNotAwaitingReviewError,
    add_equipment_line,
    get_event_request_for_organiser,
    list_equipment_lines,
    remove_equipment_line,
    update_equipment_line,
)

pytestmark = pytest.mark.scrum_37

MakeEventRequest = Callable[..., EventRequest]
MakeEquipmentLine = Callable[..., EventEquipmentLine]
ReloadEquipmentLine = Callable[[int], EventEquipmentLine]
Save = Callable[..., None]
StoredLine = tuple[int, int, int, str | None, EquipmentLineStatus]
LineOperation = Callable[[int, str, int], None]

#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
TECHNICAL_SUPPORT_ID = 5
REFERENCE = "EVR-AAAAAAAA"
OTHER_REFERENCE = "EVR-BBBBBBBB"
UNKNOWN_REFERENCE = "EVR-ZZZZZZZZ"
UNKNOWN_ID = 999
REQUESTED = EquipmentLineStatus.REQUESTED
#: A draft is out of scope here: it is hidden from coordinators altogether
#: (SCRUM-20, ADR-0024), not merely refused as "not awaiting review".
NO_LONGER_AWAITING_REVIEW = [
    EventRequestStatus.CONFIRMED,
    EventRequestStatus.COMPLETED,
    EventRequestStatus.CANCELLED,
    EventRequestStatus.REJECTED,
]


def _stored_lines(session: Session) -> list[StoredLine]:
    """Every saved line, read back from the database, in the order they were added."""
    session.expire_all()
    stored = []
    for line in session.scalars(select(EventEquipmentLine).order_by(EventEquipmentLine.id)):
        stored.append(
            (line.event_request_id, line.equipment_type_id, line.quantity, line.notes, line.status)
        )
    return stored


def _listed_by_the_coordinator(reference: str) -> tuple[EventRequest, list[EventEquipmentLine]]:
    """List ``reference``'s lines as the coordinator it is assigned to."""
    return list_equipment_lines(COORDINATOR_ID, reference, viewer_role=Role.EVENT_COORDINATOR)


def _add_rejected(session: Session, payload: dict[str, Any]) -> ValidationError:
    """Add ``payload`` to REFERENCE, expecting a 400 that saves nothing."""
    with pytest.raises(ValidationError) as exc_info:
        add_equipment_line(COORDINATOR_ID, REFERENCE, payload)

    assert exc_info.value.status_code == 400
    assert _stored_lines(session) == []
    return exc_info.value


def _edit_rejected(
    reload: ReloadEquipmentLine, line: EventEquipmentLine, payload: dict[str, Any]
) -> ValidationError:
    """Edit ``line`` with ``payload``, expecting a 400 that changes nothing."""
    before = EquipmentLineSchema().dump(reload(line.id))

    with pytest.raises(ValidationError) as exc_info:
        update_equipment_line(COORDINATOR_ID, REFERENCE, line.id, payload)

    assert exc_info.value.status_code == 400
    assert EquipmentLineSchema().dump(reload(line.id)) == before
    return exc_info.value


def _edit_quantity(coordinator_id: int, reference: str, line_id: int) -> None:
    """Edit a line's quantity: one of the two operations on an existing line."""
    update_equipment_line(coordinator_id, reference, line_id, {"quantity": 3})


#: What can be done to an existing line (AC2). Both refuse the same things.
LINE_OPERATIONS = [_edit_quantity, remove_equipment_line]
LINE_OPERATION_IDS = ["edit", "remove"]


@pytest.fixture()
def saved_line(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Save,
) -> EventEquipmentLine:
    """Two projectors on REFERENCE, noted "Needs HDMI"."""
    line = make_equipment_line(saved_event_request, equipment_type)
    save(line)
    return line


@pytest.fixture()
def other_event_request(make_event_request: MakeEventRequest, save: Save) -> EventRequest:
    """A second saved request, OTHER_REFERENCE, assigned to the same coordinator."""
    event_request = make_event_request(reference=OTHER_REFERENCE, coordinator_id=COORDINATOR_ID)
    save(event_request)
    return event_request


@pytest.fixture(
    params=[(9, COORDINATOR_ID), (COORDINATOR_ID, None)],
    ids=["another-coordinators-event", "an-unassigned-event"],
)
def outside_coordinator(
    request: pytest.FixtureRequest, saved_event_request: EventRequest, save: Save
) -> int:
    """The id of a coordinator who isn't REFERENCE's assigned coordinator.

    Either REFERENCE is assigned to coordinator 3 and the caller is coordinator 9, or
    REFERENCE is unassigned and the caller is coordinator 3.
    """
    caller_id, assigned_to = request.param
    saved_event_request.coordinator_id = assigned_to
    save(saved_event_request)
    return caller_id


# --------------------------------------------------------------------------
# AC1 — one or more lines, each with a type, a quantity and technical notes
# --------------------------------------------------------------------------


def test_a_line_is_saved_with_its_type_quantity_notes_and_requested_status(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    valid_equipment_line_payload: dict[str, Any],
    reload_equipment_line: ReloadEquipmentLine,
) -> None:
    line = add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)

    reloaded = reload_equipment_line(line.id)
    assert EquipmentLineSchema().dump(reloaded) == {
        "id": line.id,
        "equipment_type_id": equipment_type.id,
        "quantity": 2,
        "notes": "Needs HDMI",
        "status": "requested",
    }
    assert reloaded.event_request_id == saved_event_request.id


def test_several_lines_of_different_types_can_be_added(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    valid_equipment_line_payload: dict[str, Any],
) -> None:
    add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)
    add_equipment_line(
        COORDINATOR_ID, REFERENCE, {"equipment_type_id": microphone.id, "quantity": 4}
    )

    event_id = saved_event_request.id
    assert _stored_lines(db_session) == [
        (event_id, equipment_type.id, 2, "Needs HDMI", REQUESTED),
        (event_id, microphone.id, 4, None, REQUESTED),
    ]


@pytest.mark.parametrize(
    "notes",
    [{"notes": None}, {"notes": ""}, {"notes": "   "}, {}],
    ids=["null", "empty", "whitespace", "left-out"],
)
def test_notes_are_optional_and_blank_notes_are_stored_as_null(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    reload_equipment_line: ReloadEquipmentLine,
    notes: dict[str, Any],
) -> None:
    payload = {"equipment_type_id": equipment_type.id, "quantity": 2, **notes}

    line = add_equipment_line(COORDINATOR_ID, REFERENCE, payload)

    assert reload_equipment_line(line.id).notes is None


def test_notes_are_trimmed(
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    reload_equipment_line: ReloadEquipmentLine,
) -> None:
    valid_equipment_line_payload["notes"] = "  Needs HDMI  "

    line = add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)

    assert reload_equipment_line(line.id).notes == "Needs HDMI"


@pytest.mark.parametrize("missing", ["equipment_type_id", "quantity"])
def test_missing_type_or_quantity_is_rejected(
    db_session: Session,
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    missing: str,
) -> None:
    del valid_equipment_line_payload[missing]

    error = _add_rejected(db_session, valid_equipment_line_payload)

    assert missing in error.details


def test_an_unknown_equipment_type_is_rejected(
    db_session: Session,
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
) -> None:
    valid_equipment_line_payload["equipment_type_id"] = UNKNOWN_ID

    error = _add_rejected(db_session, valid_equipment_line_payload)

    assert error.details == {"equipment_type_id": ["Equipment type not found."]}


@pytest.mark.parametrize("equipment_type_id", [0, -1, "1", 1.5, True])
def test_equipment_type_id_must_be_a_positive_whole_number(
    db_session: Session,
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    equipment_type_id: Any,
) -> None:
    valid_equipment_line_payload["equipment_type_id"] = equipment_type_id

    error = _add_rejected(db_session, valid_equipment_line_payload)

    assert list(error.details) == ["equipment_type_id"]


def test_a_second_line_for_the_same_equipment_type_is_a_conflict(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    valid_equipment_line_payload: dict[str, Any],
) -> None:
    add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)

    with pytest.raises(ConflictError) as exc_info:
        add_equipment_line(
            COORDINATOR_ID, REFERENCE, {"equipment_type_id": equipment_type.id, "quantity": 5}
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == DUPLICATE_LINE_MESSAGE
    assert _stored_lines(db_session) == [
        (saved_event_request.id, equipment_type.id, 2, "Needs HDMI", REQUESTED)
    ]


def test_adding_to_an_unknown_event_request_is_not_found(
    db_session: Session,
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        add_equipment_line(COORDINATOR_ID, UNKNOWN_REFERENCE, valid_equipment_line_payload)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Event request not found."
    assert _stored_lines(db_session) == []


@pytest.mark.parametrize("typed", ["evr-aaaaaaaa", " EVR-AAAAAAAA "])
def test_the_reference_ignores_case_and_surrounding_spaces(
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    reload_equipment_line: ReloadEquipmentLine,
    typed: str,
) -> None:
    line = add_equipment_line(COORDINATOR_ID, typed, valid_equipment_line_payload)

    assert reload_equipment_line(line.id).event_request_id == saved_event_request.id


def test_status_cannot_be_set_by_the_client(
    db_session: Session,
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
) -> None:
    valid_equipment_line_payload["status"] = "reserved"

    error = _add_rejected(db_session, valid_equipment_line_payload)

    assert error.details == {"status": ["Unknown field."]}


# --------------------------------------------------------------------------
# AC3 — a quantity of zero or less is refused
# --------------------------------------------------------------------------


@pytest.mark.parametrize("quantity", [0, -1, -100])
def test_a_quantity_of_zero_or_less_is_refused(
    db_session: Session,
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    quantity: int,
) -> None:
    valid_equipment_line_payload["quantity"] = quantity

    error = _add_rejected(db_session, valid_equipment_line_payload)

    assert error.details == {"quantity": ["Quantity must be at least 1."]}


def test_a_quantity_of_one_is_accepted(
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    reload_equipment_line: ReloadEquipmentLine,
) -> None:
    valid_equipment_line_payload["quantity"] = 1

    line = add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)

    assert reload_equipment_line(line.id).quantity == 1


@pytest.mark.parametrize("quantity", ["2", 2.5, True])
def test_quantity_must_be_a_whole_number(
    db_session: Session,
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    quantity: Any,
) -> None:
    valid_equipment_line_payload["quantity"] = quantity

    error = _add_rejected(db_session, valid_equipment_line_payload)

    assert list(error.details) == ["quantity"]


@pytest.mark.parametrize("quantity", [0, -1])
def test_editing_to_a_quantity_of_zero_or_less_is_refused_and_changes_nothing(
    saved_line: EventEquipmentLine, reload_equipment_line: ReloadEquipmentLine, quantity: int
) -> None:
    error = _edit_rejected(reload_equipment_line, saved_line, {"quantity": quantity})

    assert error.details == {"quantity": ["Quantity must be at least 1."]}


# --------------------------------------------------------------------------
# AC2 — a line can be edited or removed while the request awaits review
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "quantity", "notes"),
    [({"quantity": 5}, 5, "Needs HDMI"), ({"notes": "  Two spares  "}, 2, "Two spares")],
    ids=["quantity", "notes"],
)
def test_editing_changes_only_the_fields_sent(
    saved_line: EventEquipmentLine,
    equipment_type: EquipmentType,
    reload_equipment_line: ReloadEquipmentLine,
    payload: dict[str, Any],
    quantity: int,
    notes: str,
) -> None:
    update_equipment_line(COORDINATOR_ID, REFERENCE, saved_line.id, payload)

    reloaded = reload_equipment_line(saved_line.id)
    assert (reloaded.equipment_type_id, reloaded.quantity, reloaded.notes) == (
        equipment_type.id,
        quantity,
        notes,
    )


def test_editing_can_move_a_line_to_another_equipment_type(
    saved_line: EventEquipmentLine,
    microphone: EquipmentType,
    reload_equipment_line: ReloadEquipmentLine,
) -> None:
    update_equipment_line(
        COORDINATOR_ID, REFERENCE, saved_line.id, {"equipment_type_id": microphone.id}
    )

    assert reload_equipment_line(saved_line.id).equipment_type_id == microphone.id


@pytest.mark.parametrize(
    ("payload", "notes"),
    [({"notes": None}, None), ({"quantity": 3}, "Needs HDMI")],
    ids=["sent-as-null", "left-out"],
)
def test_editing_clears_the_notes_only_when_sent_as_null(
    saved_line: EventEquipmentLine,
    reload_equipment_line: ReloadEquipmentLine,
    payload: dict[str, Any],
    notes: str | None,
) -> None:
    update_equipment_line(COORDINATOR_ID, REFERENCE, saved_line.id, payload)

    assert reload_equipment_line(saved_line.id).notes == notes


def test_editing_to_an_unknown_equipment_type_is_rejected_and_changes_nothing(
    saved_line: EventEquipmentLine, reload_equipment_line: ReloadEquipmentLine
) -> None:
    error = _edit_rejected(reload_equipment_line, saved_line, {"equipment_type_id": UNKNOWN_ID})

    assert error.details == {"equipment_type_id": ["Equipment type not found."]}


def test_editing_to_a_type_another_line_already_has_is_a_conflict(
    saved_event_request: EventRequest,
    saved_line: EventEquipmentLine,
    microphone: EquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Save,
    reload_equipment_line: ReloadEquipmentLine,
) -> None:
    microphone_line = make_equipment_line(saved_event_request, microphone, quantity=4)
    save(microphone_line)

    with pytest.raises(ConflictError) as exc_info:
        update_equipment_line(
            COORDINATOR_ID,
            REFERENCE,
            microphone_line.id,
            {"equipment_type_id": saved_line.equipment_type_id},
        )

    assert exc_info.value.status_code == 409
    assert reload_equipment_line(microphone_line.id).equipment_type_id == microphone.id


def test_removing_a_line_deletes_only_that_line(
    db_session: Session,
    saved_event_request: EventRequest,
    saved_line: EventEquipmentLine,
    microphone: EquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Save,
) -> None:
    microphone_line = make_equipment_line(saved_event_request, microphone, quantity=4, notes=None)
    save(microphone_line)

    remove_equipment_line(COORDINATOR_ID, REFERENCE, saved_line.id)

    assert _stored_lines(db_session) == [
        (saved_event_request.id, microphone.id, 4, None, REQUESTED)
    ]


@pytest.mark.parametrize("operation", LINE_OPERATIONS, ids=LINE_OPERATION_IDS)
def test_an_unknown_line_is_not_found(
    saved_line: EventEquipmentLine, operation: LineOperation
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        operation(COORDINATOR_ID, REFERENCE, UNKNOWN_ID)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Equipment line not found."


@pytest.mark.parametrize("operation", LINE_OPERATIONS, ids=LINE_OPERATION_IDS)
@pytest.mark.parametrize(
    ("reference", "message"),
    [(REFERENCE, "Equipment line not found."), (UNKNOWN_REFERENCE, "Event request not found.")],
    ids=["another-event", "unknown-event"],
)
def test_a_line_can_only_be_reached_through_its_own_event(
    db_session: Session,
    saved_event_request: EventRequest,
    other_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Save,
    operation: LineOperation,
    reference: str,
    message: str,
) -> None:
    other_line = make_equipment_line(other_event_request, equipment_type)
    save(other_line)

    with pytest.raises(NotFoundError) as exc_info:
        operation(COORDINATOR_ID, reference, other_line.id)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == message
    assert _stored_lines(db_session) == [
        (other_event_request.id, equipment_type.id, 2, "Needs HDMI", REQUESTED)
    ]


@pytest.mark.parametrize(
    "status",
    [EventRequestStatus.SUBMITTED, EventRequestStatus.UNDER_REVIEW],
    ids=lambda status: status.value,
)
def test_lines_may_change_while_the_request_is_submitted_or_under_review(
    db_session: Session,
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    save: Save,
    status: EventRequestStatus,
) -> None:
    saved_event_request.status = status
    save(saved_event_request)

    line = add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)
    edited = update_equipment_line(COORDINATOR_ID, REFERENCE, line.id, {"quantity": 3})
    remove_equipment_line(COORDINATOR_ID, REFERENCE, line.id)

    assert edited.quantity == 3
    assert _stored_lines(db_session) == []


@pytest.mark.parametrize("status", NO_LONGER_AWAITING_REVIEW, ids=lambda status: status.value)
def test_lines_cannot_be_added_once_the_request_is_no_longer_awaiting_review(
    db_session: Session,
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    save: Save,
    status: EventRequestStatus,
) -> None:
    saved_event_request.status = status
    save(saved_event_request)

    with pytest.raises(RequestNotAwaitingReviewError) as exc_info:
        add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "request_not_awaiting_review"
    assert exc_info.value.message == NOT_AWAITING_REVIEW_MESSAGE
    assert _stored_lines(db_session) == []


@pytest.mark.parametrize("operation", LINE_OPERATIONS, ids=LINE_OPERATION_IDS)
def test_lines_cannot_be_edited_or_removed_once_the_request_is_no_longer_awaiting_review(
    saved_event_request: EventRequest,
    saved_line: EventEquipmentLine,
    save: Save,
    reload_equipment_line: ReloadEquipmentLine,
    operation: LineOperation,
) -> None:
    saved_event_request.status = EventRequestStatus.CONFIRMED
    save(saved_event_request)

    with pytest.raises(RequestNotAwaitingReviewError) as exc_info:
        operation(COORDINATOR_ID, REFERENCE, saved_line.id)

    assert exc_info.value.status_code == 409
    assert reload_equipment_line(saved_line.id).quantity == 2


# --------------------------------------------------------------------------
# AC4 — the lines and their current state are visible on the event record
# --------------------------------------------------------------------------


def test_the_events_lines_are_listed_with_their_state_in_the_order_added(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    valid_equipment_line_payload: dict[str, Any],
) -> None:
    add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)
    add_equipment_line(
        COORDINATOR_ID, REFERENCE, {"equipment_type_id": microphone.id, "quantity": 4}
    )

    _, lines = _listed_by_the_coordinator(REFERENCE)

    listed = []
    for line in lines:
        listed.append((line.equipment_type_id, line.quantity, line.status))

    assert listed == [(equipment_type.id, 2, REQUESTED), (microphone.id, 4, REQUESTED)]


def test_another_events_lines_are_not_listed(
    saved_line: EventEquipmentLine,
    other_event_request: EventRequest,
    microphone: EquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Save,
) -> None:
    save(make_equipment_line(other_event_request, microphone))

    _, lines = _listed_by_the_coordinator(REFERENCE)

    listed_ids = [line.id for line in lines]

    assert listed_ids == [saved_line.id]


def test_the_lines_come_with_the_event_they_are_needed_for(
    saved_event_request: EventRequest, other_event_request: EventRequest
) -> None:
    """Technical Support read the event's date and times from it (ADR-0019)."""
    listed_event, _ = _listed_by_the_coordinator(" evr-aaaaaaaa ")

    assert listed_event.id == saved_event_request.id


def test_listing_an_unknown_event_request_is_not_found(
    saved_event_request: EventRequest,
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        _listed_by_the_coordinator(UNKNOWN_REFERENCE)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Event request not found."


def test_the_organisers_own_event_record_shows_its_equipment_lines(
    saved_users: list[User],
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    valid_equipment_line_payload: dict[str, Any],
) -> None:
    line = add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)

    event_record = EventRequestDetailSchema().dump(get_event_request_for_organiser("7", REFERENCE))

    assert event_record["equipment_lines"] == [
        {
            "id": line.id,
            "equipment_type_id": equipment_type.id,
            "quantity": 2,
            "notes": "Needs HDMI",
            "status": "requested",
        }
    ]


# --------------------------------------------------------------------------
# ADR-0019 — only the assigned coordinator changes or lists an event's lines
# --------------------------------------------------------------------------


def _assert_event_not_found(exc_info: pytest.ExceptionInfo[NotFoundError]) -> None:
    """The refusal looks exactly like an unknown event (ADR-0012's "not yours")."""
    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Event request not found."


def test_a_coordinator_cannot_add_lines_to_an_event_not_assigned_to_them(
    db_session: Session,
    outside_coordinator: int,
    valid_equipment_line_payload: dict[str, Any],
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        add_equipment_line(outside_coordinator, REFERENCE, valid_equipment_line_payload)

    _assert_event_not_found(exc_info)
    assert _stored_lines(db_session) == []


@pytest.mark.parametrize("operation", LINE_OPERATIONS, ids=LINE_OPERATION_IDS)
def test_a_coordinator_cannot_edit_or_remove_lines_of_an_event_not_assigned_to_them(
    db_session: Session,
    saved_line: EventEquipmentLine,
    outside_coordinator: int,
    operation: LineOperation,
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        operation(outside_coordinator, REFERENCE, saved_line.id)

    _assert_event_not_found(exc_info)
    assert _stored_lines(db_session) == [
        (saved_line.event_request_id, saved_line.equipment_type_id, 2, "Needs HDMI", REQUESTED)
    ]


def test_a_coordinator_cannot_list_lines_of_an_event_not_assigned_to_them(
    saved_line: EventEquipmentLine, outside_coordinator: int
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        list_equipment_lines(outside_coordinator, REFERENCE, viewer_role=Role.EVENT_COORDINATOR)

    _assert_event_not_found(exc_info)


def test_technical_support_can_list_the_lines_of_any_event(
    saved_line: EventEquipmentLine, outside_coordinator: int
) -> None:
    """Whoever the event is assigned to, if anyone (ADR-0019)."""
    listed_event, lines = list_equipment_lines(
        TECHNICAL_SUPPORT_ID, REFERENCE, viewer_role=Role.TECHNICAL_SUPPORT_STAFF
    )

    assert listed_event.reference == REFERENCE
    assert [line.id for line in lines] == [saved_line.id]


# --------------------------------------------------------------------------
# ADR-0019 — the database holds the same rules
# --------------------------------------------------------------------------


def test_the_database_refuses_a_quantity_below_one(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Save,
) -> None:
    with pytest.raises(IntegrityError):
        save(make_equipment_line(saved_event_request, equipment_type, quantity=0))


def test_the_database_refuses_a_second_line_for_the_same_equipment_type(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    saved_line: EventEquipmentLine,
    make_equipment_line: MakeEquipmentLine,
    save: Save,
) -> None:
    with pytest.raises(IntegrityError):
        save(make_equipment_line(saved_event_request, equipment_type, quantity=5))
