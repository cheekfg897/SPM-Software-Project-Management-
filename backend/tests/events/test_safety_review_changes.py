"""Unit tests for SCRUM-33 AC9: a significant change made in Safety Review.

AC9: given the event is in Safety Review, when a significant change is made, then the
Safety Officer is notified, naming the event and the fields that changed. If the change
leaves an equipment line without a current outcome or a venue arrangement that is not
Approved, the event returns to Approved and re-enters Safety Review only once it meets
SCRUM-97 again (ADR-0107).

A significant change is an edit to a significant field (AC2) or a line added, changed
or removed (SCRUM-37 AC4). An edit can leave an arrangement unsettled only by flagging
it (AC6, ADR-0094); a line added or changed has no outcome (ADR-0092). Every Safety
Officer is told once the change is saved, as when an event enters Safety Review
(SCRUM-97 AC4).

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, organiser 7, assigned to Event Coordinator 3; 2026-10-15,
09:00-17:00, for 250 people), so the notices and the flags are real rows.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest

from app.common.errors import ConflictError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment.models import EquipmentType
from app.modules.events import services as events_services
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    EDITABLE_STATUSES,
    EventEdit,
    SafetyReviewNotAllowedError,
    add_equipment_line,
    remove_equipment_line,
    submit_for_safety_review,
    update_equipment_line,
)
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationSchema
from app.modules.notifications.services import NotificationKind, list_notifications_for_recipient
from app.modules.venue import services as venue_services
from app.modules.venue.models import BookingRequestStatus
from tests.events.cases import LOST_CONNECTION, Arrange

pytestmark = pytest.mark.scrum_33

EditEvent = Callable[[int, dict[str, Any] | None], EventEdit]
ReloadEventRequest = Callable[[int], EventRequest]
ApprovedForSafety = Callable[[EventRequestStatus], EventRequest]
WithdrawalsOf = Callable[[int], list[tuple[int | None, dict[str, Any] | None]]]

REFERENCE = "EVR-AAAAAAAA"
COORDINATOR_ID = 3
SAFETY_OFFICER_IDS = [21, 22]
CHANGED = NotificationKind.SAFETY_REVIEW_EVENT_CHANGED
BACK_IN_PLANNING = " It is back in planning until it can be sent to Safety Review again."

#: One changed value for each significant field, written out, and what the notice says
#: changed: a new proposed date moves the end date with it (ADR-0025).
SIGNIFICANT_CHANGES = [
    ({"proposed_date": "2026-10-20"}, "Changed: proposed date, end date."),
    ({"end_date": "2026-10-16"}, "Changed: end date."),
    ({"start_time": "08:00"}, "Changed: start time."),
    ({"end_time": "18:00"}, "Changed: end time."),
    ({"expected_attendance": 300}, "Changed: expected attendance."),
    ({"venue_requirements": "Stage needed"}, "Changed: venue requirements."),
    ({"equipment_requirements": "4 mics"}, "Changed: equipment requirements."),
]
#: The edits that flag every venue arrangement: timing and venue requirements (ADR-0094
#: decisions 3 and 5). ``arrange``'s arrangement is for 80 of the 250 people, so a new
#: attendance never flags it (decision 4).
FLAGGING_EDITS = [
    {"proposed_date": "2026-10-20"},
    {"end_date": "2026-10-16"},
    {"start_time": "08:00"},
    {"end_time": "18:00"},
    {"venue_requirements": "Stage needed"},
]
NOT_FLAGGING_EDITS = [
    {"expected_attendance": 300},
    {"equipment_requirements": "4 mics"},
]
NOTE_FIELDS = ["description", "programme_notes", "accessibility_needs", "internal_planning_notes"]
#: Every status an edit is allowed in but Safety Review, built from the editable set.
EDITABLE_OUTSIDE_SAFETY_REVIEW = sorted(
    EDITABLE_STATUSES - {EventRequestStatus.SAFETY_REVIEW}, key=lambda status: status.value
)


@pytest.fixture()
def safety_officers(make_user: Callable[..., User], save: Callable[..., None]) -> list[User]:
    """Two Safety Officers: every one of them is told (SCRUM-97 AC4)."""
    officers = []
    for user_id in SAFETY_OFFICER_IDS:
        officers.append(
            make_user(
                email=f"safety{user_id}@example.com", role=Role.SAFETY_OFFICER, user_id=user_id
            )
        )
    save(*officers)
    return officers


@pytest.fixture()
def in_safety_review(
    saved_users: list[User],
    safety_officers: list[User],
    saved_event_request: EventRequest,
    save: Callable[..., None],
) -> EventRequest:
    """``saved_event_request`` in Safety Review, the Safety Officer not yet ruled."""
    saved_event_request.status = EventRequestStatus.SAFETY_REVIEW
    save(saved_event_request)
    return saved_event_request


@pytest.fixture()
def projector_line(
    in_safety_review: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
) -> EventEquipmentLine:
    """Two projectors on the event, with Technical Support's outcome recorded."""
    line = make_equipment_line(in_safety_review, equipment_type)
    line.provided_quantity = 2
    line.status = EquipmentLineStatus.FULFILLED
    save(line)
    return line


def _change_notices(user_id: int) -> list[Notification]:
    """The user's "changed in Safety Review" notifications, newest first."""
    notices = []
    for notification in list_notifications_for_recipient(user_id):
        if notification.kind is CHANGED:
            notices.append(notification)
    return notices


def _told(user_id: int) -> list[tuple[str, str | None]]:
    """The user's "changed in Safety Review" notices as (reference, detail)."""
    rows = []
    for notification in _change_notices(user_id):
        rows.append((notification.event_reference, notification.detail))
    return rows


def _assert_every_officer_told(detail: str) -> None:
    for officer_id in SAFETY_OFFICER_IDS:
        assert _told(officer_id) == [(REFERENCE, detail)]


def _assert_no_officer_told() -> None:
    for officer_id in SAFETY_OFFICER_IDS:
        assert _told(officer_id) == []


def _add_microphones(microphone: EquipmentType) -> None:
    add_equipment_line(
        COORDINATOR_ID, REFERENCE, {"equipment_type_id": microphone.id, "quantity": 4}
    )


def _lose_every_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every notice the change sends fail to save, the events' and Venue Staff's.

    Each lost notice rolls back what wasn't committed (ADR-0015), so whatever is still
    there afterwards was saved in the change's own commit.
    """

    def _fail(*_: Any, **__: Any) -> None:
        raise LOST_CONNECTION

    monkeypatch.setattr(events_services, "notify_users", _fail)
    monkeypatch.setattr(venue_services, "notify_users", _fail)


# --------------------------------------------------------------------------
# AC9 — every Safety Officer is told, naming the event and the fields
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "detail"),
    SIGNIFICANT_CHANGES,
    ids=[next(iter(payload)) for payload, _ in SIGNIFICANT_CHANGES],
)
def test_every_safety_officer_is_told_of_a_significant_edit_and_its_fields(
    in_safety_review: EventRequest, edit_event: EditEvent, payload: dict[str, Any], detail: str
) -> None:
    edit_event(COORDINATOR_ID, payload)

    _assert_every_officer_told(detail)


def test_the_notice_names_every_field_the_edit_changed(
    in_safety_review: EventRequest, edit_event: EditEvent
) -> None:
    """A note changed beside a significant field is named too, in the edit's order."""
    edit_event(
        COORDINATOR_ID,
        {"description": "Doors at 8", "expected_attendance": 300, "end_time": "18:00"},
    )

    _assert_every_officer_told("Changed: description, end time, expected attendance.")


def test_the_notice_says_what_it_is_and_links_to_the_event(
    in_safety_review: EventRequest, edit_event: EditEvent
) -> None:
    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    [notice] = _change_notices(SAFETY_OFFICER_IDS[0])
    shown = NotificationSchema().dump(notice)
    assert shown["message"] == "An event in Safety Review changed significantly."
    assert shown["event_name"] == in_safety_review.name
    assert shown["link"] == f"/events/{REFERENCE}"


@pytest.mark.parametrize(
    "payload",
    [
        *({field: "New notes"} for field in NOTE_FIELDS),
        {"expected_attendance": 250},
        {"description": "New notes", "start_time": "09:00"},
    ],
    ids=[*NOTE_FIELDS, "same-attendance-sent-again", "a-note-and-same-time-sent-again"],
)
def test_an_edit_that_is_not_significant_tells_nobody(
    in_safety_review: EventRequest,
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    payload: dict[str, Any],
) -> None:
    edit_event(COORDINATOR_ID, payload)

    _assert_no_officer_told()
    assert reload_event_request(in_safety_review.id).status is EventRequestStatus.SAFETY_REVIEW


@pytest.mark.parametrize("status", EDITABLE_OUTSIDE_SAFETY_REVIEW, ids=lambda status: status.value)
def test_a_significant_edit_outside_safety_review_tells_no_safety_officer(
    in_safety_review: EventRequest,
    save: Callable[..., None],
    edit_event: EditEvent,
    status: EventRequestStatus,
) -> None:
    in_safety_review.status = status
    save(in_safety_review)

    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    _assert_no_officer_told()


def test_nobody_but_the_safety_officers_hears_of_the_change(
    saved_users: list[User],
    in_safety_review: EventRequest,
    edit_event: EditEvent,
    make_user: Callable[..., User],
    save: Callable[..., None],
) -> None:
    """One user of every other role, from the enum, so a role added later is checked."""
    others = []
    for offset, role in enumerate(Role):
        if role is not Role.SAFETY_OFFICER:
            others.append(
                make_user(email=f"{role.value}@example.com", role=role, user_id=100 + offset)
            )
    save(*others)

    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    assert _told(SAFETY_OFFICER_IDS[0]) != []
    for user in [*others, *saved_users]:
        assert _told(user.id) == [], user.role


def test_a_lost_notice_does_not_lose_the_edit(
    in_safety_review: EventRequest,
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR-0015: the edit is committed before the Safety Officers are told."""
    _lose_every_notice(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    assert reload_event_request(in_safety_review.id).expected_attendance == 300
    assert [record.getMessage() for record in caplog.records] == [
        f"event_request_notification_failed reference={REFERENCE} kind=safety_review_event_changed"
    ]


# --------------------------------------------------------------------------
# AC9 — an edit that unsettles an arrangement sends the event back to Approved
# --------------------------------------------------------------------------


@pytest.mark.parametrize("payload", FLAGGING_EDITS, ids=lambda payload: next(iter(payload)))
def test_an_edit_that_flags_an_arrangement_sends_the_event_back_to_approved(
    in_safety_review: EventRequest,
    arrange: Arrange,
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    payload: dict[str, Any],
) -> None:
    """The flagged arrangement must be reconfirmed, so SCRUM-97 is no longer met."""
    arrange(BookingRequestStatus.APPROVED)

    edit = edit_event(COORDINATOR_ID, payload)

    assert edit.event_request.status is EventRequestStatus.APPROVED
    assert reload_event_request(in_safety_review.id).status is EventRequestStatus.APPROVED


def test_a_rise_in_attendance_that_outgrows_an_arrangement_sends_the_event_back_to_approved(
    in_safety_review: EventRequest,
    arrange: Arrange,
    save: Callable[..., None],
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
) -> None:
    """An arrangement for all 250 people can't hold 300, so it is flagged (ADR-0094)."""
    whole_audience = arrange(BookingRequestStatus.APPROVED)
    whole_audience.expected_occupancy = 250
    save(whole_audience)

    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    assert reload_event_request(in_safety_review.id).status is EventRequestStatus.APPROVED
    _assert_every_officer_told("Changed: expected attendance." + BACK_IN_PLANNING)


@pytest.mark.parametrize("payload", NOT_FLAGGING_EDITS, ids=lambda payload: next(iter(payload)))
def test_an_edit_that_flags_nothing_leaves_the_event_in_safety_review(
    in_safety_review: EventRequest,
    arrange: Arrange,
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    payload: dict[str, Any],
) -> None:
    """The officer is told, and goes on reviewing the event as it now stands."""
    arrange(BookingRequestStatus.APPROVED)

    edit_event(COORDINATOR_ID, payload)

    assert reload_event_request(in_safety_review.id).status is EventRequestStatus.SAFETY_REVIEW
    [(_, detail)] = _told(SAFETY_OFFICER_IDS[0])
    assert detail is not None
    assert not detail.endswith(BACK_IN_PLANNING)


def test_the_notice_says_the_event_is_back_in_planning(
    in_safety_review: EventRequest, arrange: Arrange, edit_event: EditEvent
) -> None:
    arrange(BookingRequestStatus.APPROVED)

    edit_event(COORDINATOR_ID, {"start_time": "08:00"})

    _assert_every_officer_told("Changed: start time." + BACK_IN_PLANNING)


def test_it_re_enters_safety_review_only_once_scrum_97_is_met_again(
    in_safety_review: EventRequest, arrange: Arrange, edit_event: EditEvent
) -> None:
    """The flag holds it out of Safety Review until it clears (ADR-0094 decision 9)."""
    flagged = arrange(BookingRequestStatus.APPROVED)
    edit_event(COORDINATOR_ID, {"start_time": "08:00"})

    with pytest.raises(SafetyReviewNotAllowedError) as exc_info:
        submit_for_safety_review(COORDINATOR_ID, REFERENCE)

    gaps = exc_info.value.details["venue_arrangements"]
    assert gaps == [
        f"Venue arrangement {flagged.id} is flagged (requires reconfirmation): "
        "The event's date or time changed."
    ]


def test_a_withdrawn_approval_and_a_flag_move_the_event_once(
    saved_users: list[User],
    safety_officers: list[User],
    approved_for_safety: ApprovedForSafety,
    arrange: Arrange,
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    safety_withdrawals_of: WithdrawalsOf,
) -> None:
    """AC7 and AC9 together: one withdrawal, one move, one notice per officer."""
    event = approved_for_safety(EventRequestStatus.SAFETY_REVIEW)
    arrange(BookingRequestStatus.APPROVED)

    edit_event(COORDINATOR_ID, {"start_time": "08:00"})

    assert reload_event_request(event.id).status is EventRequestStatus.APPROVED
    assert len(safety_withdrawals_of(event.id)) == 1
    _assert_every_officer_told("Changed: start time." + BACK_IN_PLANNING)


def test_a_withdrawn_approval_alone_is_told_as_back_in_planning(
    saved_users: list[User],
    safety_officers: list[User],
    approved_for_safety: ApprovedForSafety,
    edit_event: EditEvent,
) -> None:
    """ADR-0087 sends it back with no flag; the officer still hears why it left."""
    approved_for_safety(EventRequestStatus.SAFETY_REVIEW)

    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    _assert_every_officer_told("Changed: expected attendance." + BACK_IN_PLANNING)


def test_the_move_back_is_saved_with_the_edit(
    in_safety_review: EventRequest,
    arrange: Arrange,
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The move rides in the edit's own commit, so losing every notice keeps it."""
    arrange(BookingRequestStatus.APPROVED)
    _lose_every_notice(monkeypatch)

    edit_event(COORDINATOR_ID, {"start_time": "08:00"})

    assert reload_event_request(in_safety_review.id).status is EventRequestStatus.APPROVED


# --------------------------------------------------------------------------
# AC9 and SCRUM-37 AC4 — a line added, changed or removed in Safety Review
# --------------------------------------------------------------------------


def test_adding_a_line_sends_the_event_back_to_approved_and_tells_the_officers(
    in_safety_review: EventRequest,
    microphone: EquipmentType,
    reload_event_request: ReloadEventRequest,
) -> None:
    """The new line has no outcome, so SCRUM-97 is no longer met."""
    _add_microphones(microphone)

    assert reload_event_request(in_safety_review.id).status is EventRequestStatus.APPROVED
    _assert_every_officer_told("Changed: equipment line." + BACK_IN_PLANNING)


@pytest.mark.parametrize("field", ["quantity", "equipment_type_id"])
def test_changing_a_line_sends_the_event_back_to_approved_and_tells_the_officers(
    projector_line: EventEquipmentLine,
    microphone: EquipmentType,
    reload_event_request: ReloadEventRequest,
    field: str,
) -> None:
    """The changed line's outcome is cleared (ADR-0092): SCRUM-97 is no longer met."""
    change_by_field = {
        "quantity": {"quantity": 3},
        "equipment_type_id": {"equipment_type_id": microphone.id},
    }

    update_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id, change_by_field[field])

    status = reload_event_request(projector_line.event_request_id).status
    assert status is EventRequestStatus.APPROVED
    _assert_every_officer_told("Changed: equipment line." + BACK_IN_PLANNING)


@pytest.mark.parametrize(
    "payload",
    [{"notes": "Bring spare bulbs"}, {"quantity": 2}],
    ids=["notes-only", "same-quantity-sent-again"],
)
def test_a_line_change_that_is_not_significant_tells_nobody(
    projector_line: EventEquipmentLine,
    reload_event_request: ReloadEventRequest,
    payload: dict[str, Any],
) -> None:
    update_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id, payload)

    status = reload_event_request(projector_line.event_request_id).status
    assert status is EventRequestStatus.SAFETY_REVIEW
    _assert_no_officer_told()


def test_removing_a_line_tells_the_officers_and_leaves_the_event_in_safety_review(
    projector_line: EventEquipmentLine, reload_event_request: ReloadEventRequest
) -> None:
    """A removed line leaves no line without an outcome (SCRUM-37 AC4)."""
    remove_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id)

    status = reload_event_request(projector_line.event_request_id).status
    assert status is EventRequestStatus.SAFETY_REVIEW
    _assert_every_officer_told("Changed: equipment line.")


@pytest.mark.parametrize("status", EDITABLE_OUTSIDE_SAFETY_REVIEW, ids=lambda status: status.value)
def test_a_line_change_outside_safety_review_tells_no_safety_officer(
    projector_line: EventEquipmentLine,
    in_safety_review: EventRequest,
    microphone: EquipmentType,
    save: Callable[..., None],
    reload_event_request: ReloadEventRequest,
    status: EventRequestStatus,
) -> None:
    in_safety_review.status = status
    save(in_safety_review)

    _add_microphones(microphone)
    update_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id, {"quantity": 3})
    remove_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id)

    _assert_no_officer_told()
    assert reload_event_request(in_safety_review.id).status is status


def test_a_line_refused_as_a_duplicate_moves_nothing_and_tells_nobody(
    projector_line: EventEquipmentLine,
    equipment_type: EquipmentType,
    reload_event_request: ReloadEventRequest,
) -> None:
    """The move rides in the line's commit: a refused line leaves the event alone."""
    with pytest.raises(ConflictError):
        add_equipment_line(
            COORDINATOR_ID, REFERENCE, {"equipment_type_id": equipment_type.id, "quantity": 1}
        )

    status = reload_event_request(projector_line.event_request_id).status
    assert status is EventRequestStatus.SAFETY_REVIEW
    _assert_no_officer_told()


def test_the_move_back_is_saved_with_the_added_line(
    in_safety_review: EventRequest,
    microphone: EquipmentType,
    reload_event_request: ReloadEventRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The move rides in the line's own commit, so losing every notice keeps it."""
    _lose_every_notice(monkeypatch)

    _add_microphones(microphone)

    assert reload_event_request(in_safety_review.id).status is EventRequestStatus.APPROVED


def test_a_line_added_after_the_safety_approval_moves_the_event_once(
    saved_users: list[User],
    safety_officers: list[User],
    approved_for_safety: ApprovedForSafety,
    microphone: EquipmentType,
    reload_event_request: ReloadEventRequest,
    safety_withdrawals_of: WithdrawalsOf,
) -> None:
    event = approved_for_safety(EventRequestStatus.SAFETY_REVIEW)

    _add_microphones(microphone)

    assert reload_event_request(event.id).status is EventRequestStatus.APPROVED
    assert len(safety_withdrawals_of(event.id)) == 1
    _assert_every_officer_told("Changed: equipment line." + BACK_IN_PLANNING)
