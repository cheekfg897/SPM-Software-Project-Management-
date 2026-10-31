"""Unit tests for SCRUM-37 "Record what equipment an event needs": a line change.

AC4: adding a line, changing its quantity or removing it is a significant change
(SCRUM-33). It is written to the event's history as a significant ``field_changed``
entry on ``equipment_line``. A new or changed line has no current outcome and awaits
Technical Support's review again; an outcome it had stays in the history. Technical
Support Staff are told, and the event cannot enter Safety Review or be confirmed until
every remaining line has an outcome again. Changing a line's equipment type counts as
changing what it asks for; changing only its technical notes does not (ADR-0019,
ADR-0092). A removed line's reservation is in ``test_equipment_line_releases.py``.

The services run against ``db_session``, so the history, the notifications and the
gates read what the line change saved.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.common.errors import AppError
from app.modules.auth.models import User
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    EventConfirmationNotAllowedError,
    SafetyReviewNotAllowedError,
    add_equipment_line,
    confirm_event_request,
    record_equipment_outcome,
    remove_equipment_line,
    submit_for_safety_review,
    update_equipment_line,
)
from app.modules.notifications.services import NotificationKind
from app.modules.venue.models import BookingRequestStatus
from tests.conftest import approve_safety
from tests.events.cases import Arrange

#: Each test starts on an approved event, the first status its equipment lines change
#: in (SCRUM-110); a test that needs another status sets it.
pytestmark = [pytest.mark.scrum_37, pytest.mark.usefixtures("approved_event_request")]

HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]
ReloadEquipmentLine = Callable[[int], EventEquipmentLine]
Save = Callable[..., None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
#: The Technical Support Staff in ``saved_users``.
TECHNICAL_SUPPORT_IDS = [2, 5]


def _line_changes(
    history: list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]],
) -> list[tuple[int | None, dict[str, Any]]]:
    """The ``field_changed`` entries about a line, as ``(actor_id, details)``."""
    changes = []
    for kind, actor_id, details in history:
        if kind is EventHistoryKind.FIELD_CHANGED and details["field"] == "equipment_line":
            changes.append((actor_id, details))
    return changes


def _kinds_of(notifications: list[tuple[Any, ...]]) -> list[NotificationKind]:
    """Each notification's kind, newest first."""
    return [notification[3] for notification in notifications]


def _outcome(line: EventEquipmentLine) -> tuple[Any, ...]:
    """Everything a line's outcome is made of, beside its status."""
    return (
        line.status,
        line.provided_quantity,
        line.outcome_note,
        line.reviewed_by,
        line.reviewed_at,
    )


@pytest.fixture()
def projector_line(
    saved_users: list[User],
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Save,
) -> EventEquipmentLine:
    """Ten projectors on REFERENCE, with no outcome yet."""
    line = make_equipment_line(saved_event_request, equipment_type, quantity=10)
    save(line)
    return line


@pytest.fixture()
def reviewed_line(projector_line: EventEquipmentLine) -> EventEquipmentLine:
    """``projector_line``, of which Technical Support user 5 will provide six."""
    payload = {"provided_quantity": 6, "note": "Only six in stock"}
    return record_equipment_outcome(5, REFERENCE, projector_line.id, payload)


@pytest.fixture(params=["lower-quantity", "higher-quantity", "equipment-type"])
def new_request(request: pytest.FixtureRequest, microphone: EquipmentType) -> dict[str, Any]:
    """A body that changes what ``projector_line`` asks for.

    The lower quantity is below the six Technical Support were going to provide.
    """
    payloads = {
        "lower-quantity": {"quantity": 4},
        "higher-quantity": {"quantity": 12},
        "equipment-type": {"equipment_type_id": microphone.id},
    }
    return payloads[request.param]


# --------------------------------------------------------------------------
# AC4 — a line change is a significant change in the event's history
# --------------------------------------------------------------------------


def test_adding_a_line_is_recorded_as_a_significant_change(
    saved_users: list[User],
    saved_event_request: EventRequest,
    microphone: EquipmentType,
    history_of: HistoryOf,
) -> None:
    add_equipment_line(
        COORDINATOR_ID, REFERENCE, {"equipment_type_id": microphone.id, "quantity": 4}
    )

    assert _line_changes(history_of(saved_event_request.id)) == [
        (
            COORDINATOR_ID,
            {
                "field": "equipment_line",
                "previous_value": None,
                "new_value": "Microphone, quantity 4",
                "significant": True,
            },
        )
    ]


@pytest.mark.parametrize(
    ("change", "new_value"),
    [
        ("quantity", "Projector, quantity 3"),
        ("equipment-type", "Microphone, quantity 10"),
        ("both", "Microphone, quantity 3"),
    ],
)
def test_changing_what_a_line_asks_for_is_recorded_as_a_significant_change(
    saved_event_request: EventRequest,
    projector_line: EventEquipmentLine,
    microphone: EquipmentType,
    history_of: HistoryOf,
    change: str,
    new_value: str,
) -> None:
    """The entry shows the line before and after, each by type name and quantity."""
    payloads = {
        "quantity": {"quantity": 3},
        "equipment-type": {"equipment_type_id": microphone.id},
        "both": {"equipment_type_id": microphone.id, "quantity": 3},
    }

    update_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id, payloads[change])

    assert _line_changes(history_of(saved_event_request.id)) == [
        (
            COORDINATOR_ID,
            {
                "field": "equipment_line",
                "previous_value": "Projector, quantity 10",
                "new_value": new_value,
                "significant": True,
            },
        )
    ]


def test_removing_a_line_is_recorded_as_a_significant_change(
    saved_event_request: EventRequest,
    projector_line: EventEquipmentLine,
    history_of: HistoryOf,
) -> None:
    remove_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id)

    assert _line_changes(history_of(saved_event_request.id)) == [
        (
            COORDINATOR_ID,
            {
                "field": "equipment_line",
                "previous_value": "Projector, quantity 10",
                "new_value": None,
                "significant": True,
            },
        )
    ]


@pytest.mark.parametrize(
    "payload",
    [{"notes": "Bring a spare bulb"}, {"quantity": 10}, {}],
    ids=["only-the-notes", "the-same-quantity", "nothing"],
)
def test_a_line_change_that_asks_for_nothing_new_is_not_a_significant_change(
    saved_event_request: EventRequest,
    reviewed_line: EventEquipmentLine,
    reload_equipment_line: ReloadEquipmentLine,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
    payload: dict[str, Any],
) -> None:
    """Nothing is recorded or reopened, and Technical Support hear nothing new."""
    outcome_before = _outcome(reload_equipment_line(reviewed_line.id))

    update_equipment_line(COORDINATOR_ID, REFERENCE, reviewed_line.id, payload)

    assert _line_changes(history_of(saved_event_request.id)) == []
    assert _outcome(reload_equipment_line(reviewed_line.id)) == outcome_before
    assert notifications_of(5) == []


# --------------------------------------------------------------------------
# AC4 — a changed line awaits Technical Support's review again
# --------------------------------------------------------------------------


def test_a_changed_line_has_no_current_outcome(
    reviewed_line: EventEquipmentLine,
    reload_equipment_line: ReloadEquipmentLine,
    new_request: dict[str, Any],
) -> None:
    update_equipment_line(COORDINATOR_ID, REFERENCE, reviewed_line.id, new_request)

    assert _outcome(reload_equipment_line(reviewed_line.id)) == (
        EquipmentLineStatus.REQUESTED,
        None,
        None,
        None,
        None,
    )


def test_a_changed_lines_earlier_outcome_stays_in_the_event_history(
    saved_event_request: EventRequest,
    reviewed_line: EventEquipmentLine,
    history_of: HistoryOf,
    new_request: dict[str, Any],
) -> None:
    update_equipment_line(COORDINATOR_ID, REFERENCE, reviewed_line.id, new_request)

    outcomes = []
    for kind, actor_id, details in history_of(saved_event_request.id):
        if kind is EventHistoryKind.EQUIPMENT_OUTCOME_RECORDED:
            outcomes.append((actor_id, details["provided_quantity"], details["note"]))
    assert outcomes == [(5, 6, "Only six in stock")]


def test_a_changed_line_holds_back_the_safety_review(
    saved_event_request: EventRequest,
    reviewed_line: EventEquipmentLine,
    arrange: Arrange,
    save: Save,
) -> None:
    """Without the change, every check would pass and the event would go through."""
    saved_event_request.status = EventRequestStatus.APPROVED
    save(saved_event_request)
    arrange(BookingRequestStatus.APPROVED)

    update_equipment_line(COORDINATOR_ID, REFERENCE, reviewed_line.id, {"quantity": 8})

    with pytest.raises(SafetyReviewNotAllowedError) as exc_info:
        submit_for_safety_review(COORDINATOR_ID, REFERENCE)
    assert exc_info.value.details == {
        "equipment": [
            f"Equipment request {reviewed_line.id} has no outcome from Technical Support."
        ]
    }


def test_a_reopened_line_holds_back_confirmation(
    saved_event_request: EventRequest,
    reviewed_line: EventEquipmentLine,
    arrange: Arrange,
    save: Save,
) -> None:
    """The line still has no outcome when the Safety Officer approves.

    The event is put in Safety Review after the change: a change made there sends it
    back to Approved (SCRUM-33 AC9, ADR-0107).
    """
    arrange(BookingRequestStatus.APPROVED)
    update_equipment_line(COORDINATOR_ID, REFERENCE, reviewed_line.id, {"quantity": 8})
    saved_event_request.status = EventRequestStatus.SAFETY_REVIEW
    save(saved_event_request)
    approve_safety(saved_event_request, save)

    with pytest.raises(EventConfirmationNotAllowedError) as exc_info:
        confirm_event_request(COORDINATOR_ID, REFERENCE)
    assert exc_info.value.details == {
        "equipment": [
            f"Equipment request {reviewed_line.id} has no outcome from Technical Support."
        ]
    }


# --------------------------------------------------------------------------
# AC4 — Technical Support Staff are told (SCRUM-60)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("technical_support_id", TECHNICAL_SUPPORT_IDS)
def test_technical_support_are_told_of_a_changed_line(
    projector_line: EventEquipmentLine,
    notifications_of: NotificationsOf,
    new_request: dict[str, Any],
    technical_support_id: int,
) -> None:
    update_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id, new_request)

    assert _kinds_of(notifications_of(technical_support_id)) == [
        NotificationKind.SIGNIFICANT_CHANGE
    ]


@pytest.mark.parametrize("technical_support_id", TECHNICAL_SUPPORT_IDS)
def test_technical_support_are_told_of_a_removed_line(
    projector_line: EventEquipmentLine,
    notifications_of: NotificationsOf,
    technical_support_id: int,
) -> None:
    remove_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id)

    assert _kinds_of(notifications_of(technical_support_id)) == [
        NotificationKind.SIGNIFICANT_CHANGE
    ]


def test_an_added_line_is_announced_once_as_requested_equipment(
    saved_users: list[User],
    saved_event_request: EventRequest,
    microphone: EquipmentType,
    notifications_of: NotificationsOf,
) -> None:
    """Not a second time as a significant change (AC6, ADR-0092)."""
    add_equipment_line(
        COORDINATOR_ID, REFERENCE, {"equipment_type_id": microphone.id, "quantity": 4}
    )

    assert _kinds_of(notifications_of(5)) == [NotificationKind.EQUIPMENT_REQUESTED]


@pytest.mark.parametrize("user_id", [3, 4, 7], ids=["coordinator", "venue-staff", "organiser"])
def test_nobody_else_is_told_of_a_line_change(
    projector_line: EventEquipmentLine,
    notifications_of: NotificationsOf,
    user_id: int,
) -> None:
    update_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id, {"quantity": 3})
    remove_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id)

    assert notifications_of(user_id) == []


def test_a_refused_line_change_records_and_reopens_nothing(
    saved_event_request: EventRequest,
    reviewed_line: EventEquipmentLine,
    microphone: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    reload_equipment_line: ReloadEquipmentLine,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
    save: Save,
) -> None:
    """A type another line already has is refused, and the whole change with it."""
    save(make_equipment_line(saved_event_request, microphone))
    outcome_before = _outcome(reload_equipment_line(reviewed_line.id))

    with pytest.raises(AppError) as exc_info:
        update_equipment_line(
            COORDINATOR_ID, REFERENCE, reviewed_line.id, {"equipment_type_id": microphone.id}
        )

    assert exc_info.value.status_code == 409
    assert _line_changes(history_of(saved_event_request.id)) == []
    assert _outcome(reload_equipment_line(reviewed_line.id)) == outcome_before
    assert notifications_of(5) == []
