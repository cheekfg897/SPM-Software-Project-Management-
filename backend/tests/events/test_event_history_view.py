"""Unit tests for SCRUM-33 "Update event information and flag significant changes".

``list_event_history``: the Lead, Venue Staff and Technical Support see any event's
history, and an Event Coordinator only their own events' (SCRUM-96 AC6), oldest first,
with every actor and coordinator name resolved and no user ids anywhere in the reply
(ADR-0025). An Event Organiser sees the same event's history for their own client
organisation only, minus any ``field_changed`` entry about
``internal_planning_notes``. A removed user's name comes back ``null``.

Runs against ``db_session`` with ``saved_users``; history entries are written
directly with ``record_event_history`` so their ``occurred_at`` values can be pinned
out of insertion order.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import (
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    list_event_history,
    record_event_history,
)

pytestmark = pytest.mark.scrum_33

REFERENCE = "EVR-AAAAAAAA"

REASSIGNED_DETAILS = {
    "previous_coordinator_id": 3,
    "previous_coordinator_name": "Coordinator Three",
    "coordinator_id": 9,
    "coordinator_name": "Coordinator Nine",
}
ATTENDANCE_CHANGED_DETAILS = {
    "field": "expected_attendance",
    "previous_value": 250,
    "new_value": 300,
    "significant": True,
}
INTERNAL_NOTE_CHANGED_DETAILS = {
    "field": "internal_planning_notes",
    "previous_value": None,
    "new_value": "Confidential",
    "significant": False,
}


@pytest.fixture()
def recorded_history(
    saved_users: list[User], saved_event_request: EventRequest, db_session: Session
) -> EventRequest:
    """Four history entries on ``saved_event_request``, written out of time order.

    Oldest first they should read: assigned (02:00), reassigned (03:00), the
    attendance change (04:00), then the internal-only note change (04:00, same
    instant, so insertion order settles the tie).
    """
    record_event_history(
        saved_event_request,
        EventHistoryKind.COORDINATOR_REASSIGNED,
        actor_id=3,
        details=REASSIGNED_DETAILS,
        session=db_session,
        now=datetime(2026, 9, 15, 3, 0, tzinfo=timezone.utc),
    )
    record_event_history(
        saved_event_request,
        EventHistoryKind.COORDINATOR_ASSIGNED,
        actor_id=None,
        details={"coordinator_id": 3},
        session=db_session,
        now=datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc),
    )
    record_event_history(
        saved_event_request,
        EventHistoryKind.FIELD_CHANGED,
        actor_id=9,
        details=ATTENDANCE_CHANGED_DETAILS,
        session=db_session,
        now=datetime(2026, 9, 15, 4, 0, tzinfo=timezone.utc),
    )
    record_event_history(
        saved_event_request,
        EventHistoryKind.FIELD_CHANGED,
        actor_id=9,
        details=INTERNAL_NOTE_CHANGED_DETAILS,
        session=db_session,
        now=datetime(2026, 9, 15, 4, 0, tzinfo=timezone.utc),
    )
    db_session.commit()
    return saved_event_request


# --------------------------------------------------------------------------
# ADR-0025 — internal staff see everything, oldest first, names resolved
# --------------------------------------------------------------------------


INTERNAL_VIEWERS = [
    (3, Role.EVENT_COORDINATOR),
    (8, Role.EVENT_COORDINATOR_LEAD),
    (4, Role.VENUE_STAFF),
    (5, Role.TECHNICAL_SUPPORT_STAFF),
]
INTERNAL_VIEWER_IDS = ["assigned-coordinator", "lead", "venue-staff", "technical-support"]


@pytest.mark.scrum_96
@pytest.mark.parametrize(
    ("viewer_id", "role"),
    INTERNAL_VIEWERS,
    ids=INTERNAL_VIEWER_IDS,
)
def test_internal_staff_see_every_entry_oldest_first_with_names_resolved(
    recorded_history: EventRequest, viewer_id: int, role: Role
) -> None:
    entries = list_event_history(viewer_id, REFERENCE, viewer_role=role)

    assert [entry.kind for entry in entries] == [
        EventHistoryKind.COORDINATOR_ASSIGNED,
        EventHistoryKind.COORDINATOR_REASSIGNED,
        EventHistoryKind.FIELD_CHANGED,
        EventHistoryKind.FIELD_CHANGED,
    ]
    assert [entry.actor_name for entry in entries] == [
        None,
        "Coordinator Three",
        "Coordinator Nine",
        "Coordinator Nine",
    ]
    assert [entry.details for entry in entries] == [
        {"coordinator_name": "Coordinator Three"},
        {"previous_coordinator_name": "Coordinator Three", "coordinator_name": "Coordinator Nine"},
        ATTENDANCE_CHANGED_DETAILS,
        INTERNAL_NOTE_CHANGED_DETAILS,
    ]


# --------------------------------------------------------------------------
# ADR-0025 — the organiser never sees a field_changed entry about internal notes
# --------------------------------------------------------------------------


def test_the_organiser_does_not_see_the_internal_planning_notes_change(
    recorded_history: EventRequest,
) -> None:
    entries = list_event_history(7, REFERENCE, viewer_role=Role.EVENT_ORGANISER)

    assert [entry.kind for entry in entries] == [
        EventHistoryKind.COORDINATOR_ASSIGNED,
        EventHistoryKind.COORDINATOR_REASSIGNED,
        EventHistoryKind.FIELD_CHANGED,
    ]
    assert entries[-1].details == ATTENDANCE_CHANGED_DETAILS


def test_an_organiser_cannot_see_another_organisations_history(
    saved_users: list[User],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
) -> None:
    other_organisations_event = make_event_request(
        reference="EVR-BBBBBBBB", organisation_id=4, coordinator_id=3
    )
    save(other_organisations_event)

    with pytest.raises(NotFoundError) as exc_info:
        list_event_history(7, "EVR-BBBBBBBB", viewer_role=Role.EVENT_ORGANISER)

    assert exc_info.value.status_code == 404


# --------------------------------------------------------------------------
# SCRUM-96 AC6 — a coordinator reads only the history of events assigned to them
# --------------------------------------------------------------------------


@pytest.mark.scrum_96
def test_a_coordinator_cannot_read_the_history_of_an_event_assigned_to_someone_else(
    recorded_history: EventRequest,
) -> None:
    """Coordinator 3 holds it, so coordinator 9 gets an unknown reference's 404."""
    with pytest.raises(NotFoundError) as unassigned_error:
        list_event_history(9, REFERENCE, viewer_role=Role.EVENT_COORDINATOR)
    with pytest.raises(NotFoundError) as unknown_error:
        list_event_history(9, "EVR-ZZZZZZZZ", viewer_role=Role.EVENT_COORDINATOR)

    assert unassigned_error.value.status_code == 404
    assert unassigned_error.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert unassigned_error.value.message == unknown_error.value.message


@pytest.mark.scrum_96
def test_a_coordinator_cannot_read_the_history_of_an_unassigned_event(
    saved_users: list[User],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
) -> None:
    save(make_event_request(reference="EVR-CCCCCCCC", coordinator_id=None))

    with pytest.raises(NotFoundError) as exc_info:
        list_event_history(3, "EVR-CCCCCCCC", viewer_role=Role.EVENT_COORDINATOR)

    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE


def test_an_unknown_reference_is_404(saved_users: list[User]) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        list_event_history(3, "EVR-ZZZZZZZZ", viewer_role=Role.EVENT_COORDINATOR)

    assert exc_info.value.status_code == 404


@pytest.mark.parametrize(("viewer_id", "role"), INTERNAL_VIEWERS, ids=INTERNAL_VIEWER_IDS)
def test_staff_never_see_a_drafts_history(
    saved_users: list[User],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
    viewer_id: int,
    role: Role,
) -> None:
    """Staff never see a draft (ADR-0024), so its history is a 404, like no request."""
    draft = make_event_request(reference="EVR-DDDDDDDD", status=EventRequestStatus.DRAFT)
    save(draft)

    with pytest.raises(NotFoundError) as exc_info:
        list_event_history(viewer_id, "EVR-DDDDDDDD", viewer_role=role)

    assert exc_info.value.status_code == 404


# --------------------------------------------------------------------------
# ADR-0025 — a removed user's name comes back null, not an error
# --------------------------------------------------------------------------


def test_a_removed_users_name_is_null(
    saved_event_request: EventRequest, db_session: Session
) -> None:
    record_event_history(
        saved_event_request,
        EventHistoryKind.COORDINATOR_ASSIGNED,
        actor_id=None,
        details={"coordinator_id": 99},
        session=db_session,
        now=datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc),
    )
    record_event_history(
        saved_event_request,
        EventHistoryKind.FIELD_CHANGED,
        actor_id=99,
        details={
            "field": "description",
            "previous_value": None,
            "new_value": "Revised",
            "significant": False,
        },
        session=db_session,
        now=datetime(2026, 9, 15, 3, 0, tzinfo=timezone.utc),
    )
    db_session.commit()

    entries = list_event_history(3, REFERENCE, viewer_role=Role.EVENT_COORDINATOR)

    assert entries[0].details == {"coordinator_name": None}
    assert entries[1].actor_name is None


def test_a_coordinator_assigned_entry_with_no_coordinator_id_shows_no_name(
    saved_event_request: EventRequest, db_session: Session
) -> None:
    """Defensive: a malformed entry still renders instead of raising."""
    record_event_history(
        saved_event_request,
        EventHistoryKind.COORDINATOR_ASSIGNED,
        actor_id=None,
        details={},
        session=db_session,
        now=datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc),
    )
    db_session.commit()

    entries = list_event_history(3, REFERENCE, viewer_role=Role.EVENT_COORDINATOR)

    assert entries[0].details == {"coordinator_name": None}


# --------------------------------------------------------------------------
# An entry with no details, and no history at all
# --------------------------------------------------------------------------


def test_an_entry_with_no_details_is_shown_with_empty_details(
    saved_event_request: EventRequest, db_session: Session
) -> None:
    record_event_history(
        saved_event_request,
        EventHistoryKind.FIELD_CHANGED,
        actor_id=3,
        details=None,
        session=db_session,
        now=datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc),
    )
    db_session.commit()

    entries = list_event_history(3, REFERENCE, viewer_role=Role.EVENT_COORDINATOR)

    assert entries[0].details == {}


def test_the_organiser_sees_a_field_changed_entry_with_no_details(
    saved_users: list[User], saved_event_request: EventRequest, db_session: Session
) -> None:
    record_event_history(
        saved_event_request,
        EventHistoryKind.FIELD_CHANGED,
        actor_id=3,
        details=None,
        session=db_session,
        now=datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc),
    )
    db_session.commit()

    entries = list_event_history(7, REFERENCE, viewer_role=Role.EVENT_ORGANISER)

    assert entries[0].details == {}


def test_no_history_is_an_empty_list(saved_event_request: EventRequest) -> None:
    assert list_event_history(3, REFERENCE, viewer_role=Role.EVENT_COORDINATOR) == []
