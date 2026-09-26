"""Unit tests for SCRUM-20 "Save and resume a draft event request" — AC4 visibility.

AC4: a draft is visible only to the Organiser who created it, and never to Event
Coordinators or Technical Support Staff (ADR-0024). Drafts run through the same
organisation scope as any other request (SCRUM-7, ADR-0020); this file covers the
extra narrowing a draft needs on top of it.

The organiser section runs against ``db_session`` with ``other_organisers``, so the
filters are real SQL. The staff section (SCRUM-30, ADR-0019, ADR-0021) is added
alongside it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import (
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    add_equipment_line,
    get_event_record_for_organiser,
    get_event_request_for_organiser,
    list_equipment_lines,
    list_event_requests_for_organiser,
    reassign_coordinator,
    remove_equipment_line,
    update_equipment_line,
)

pytestmark = pytest.mark.scrum_20

MakeEventRequest = Callable[..., EventRequest]

#: In client organisation 3, as ``saved_users`` links them.
ORGANISER_ID = 7
#: A colleague in the same organisation (``other_organisers``).
COLLEAGUE_ID = 8
#: A request that colleague has submitted, which the organiser does see.
COLLEAGUES_SUBMITTED_REFERENCE = "EVR-SSSSSSSS"

DRAFT_REFERENCE = "EVR-DDDDDDDD"

#: Every status but draft, so "past the draft stage" can be checked as a whole.
NON_DRAFT_STATUSES = [
    status for status in EventRequestStatus if status is not EventRequestStatus.DRAFT
]

#: The Event Coordinator the staff-section draft is (nominally) assigned to.
COORDINATOR_ID = 3
TECHNICAL_SUPPORT_ID = 5
#: A line id that need not exist: the draft is refused before it would be looked up.
UNKNOWN_LINE_ID = 999
COORDINATOR_NINE_EMAIL = "coordinator9@example.com"


def _references(event_requests: list[EventRequest]) -> set[str]:
    return {event_request.reference for event_request in event_requests}


# --------------------------------------------------------------------------
# Organiser section — a colleague's draft is hidden; its own author still sees it
# --------------------------------------------------------------------------


def test_a_colleagues_draft_is_not_in_the_organisers_list(
    other_organisers: list[User], make_event_request: MakeEventRequest, save: Callable[..., None]
) -> None:
    save(
        make_event_request(
            reference=DRAFT_REFERENCE, status=EventRequestStatus.DRAFT, organiser_id=COLLEAGUE_ID
        ),
        make_event_request(reference=COLLEAGUES_SUBMITTED_REFERENCE, organiser_id=COLLEAGUE_ID),
    )

    listed = list_event_requests_for_organiser(ORGANISER_ID)

    assert _references(listed) == {COLLEAGUES_SUBMITTED_REFERENCE}


@pytest.mark.parametrize(
    "open_request",
    [get_event_request_for_organiser, get_event_record_for_organiser],
    ids=["request", "record"],
)
def test_a_colleagues_draft_is_refused_as_not_found(
    other_organisers: list[User],
    make_event_request: MakeEventRequest,
    save: Callable[..., None],
    open_request: Callable[..., Any],
) -> None:
    save(
        make_event_request(
            reference=DRAFT_REFERENCE, status=EventRequestStatus.DRAFT, organiser_id=COLLEAGUE_ID
        )
    )

    with pytest.raises(NotFoundError) as exc_info:
        open_request(ORGANISER_ID, DRAFT_REFERENCE)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE


def test_the_author_can_open_their_own_draft(
    saved_users: list[User], make_event_request: MakeEventRequest, save: Callable[..., None]
) -> None:
    save(
        make_event_request(
            reference=DRAFT_REFERENCE, status=EventRequestStatus.DRAFT, organiser_id=ORGANISER_ID
        )
    )

    found = get_event_request_for_organiser(ORGANISER_ID, DRAFT_REFERENCE)

    assert found.reference == DRAFT_REFERENCE
    assert found.status is EventRequestStatus.DRAFT


@pytest.mark.parametrize("status", NON_DRAFT_STATUSES, ids=lambda status: status.value)
def test_colleagues_still_see_each_others_requests_past_the_draft_stage(
    other_organisers: list[User],
    make_event_request: MakeEventRequest,
    save: Callable[..., None],
    status: EventRequestStatus,
) -> None:
    save(make_event_request(reference=DRAFT_REFERENCE, status=status, organiser_id=COLLEAGUE_ID))

    listed = list_event_requests_for_organiser(ORGANISER_ID)

    assert DRAFT_REFERENCE in _references(listed)


# --------------------------------------------------------------------------
# Staff section — internal staff can't reach a draft by its reference (ADR-0024)
# --------------------------------------------------------------------------


def _list_as_technical_support(reference: str) -> Any:
    return list_equipment_lines(
        TECHNICAL_SUPPORT_ID, reference, viewer_role=Role.TECHNICAL_SUPPORT_STAFF
    )


def _list_as_coordinator(reference: str) -> Any:
    return list_equipment_lines(COORDINATOR_ID, reference, viewer_role=Role.EVENT_COORDINATOR)


def _add_a_line(reference: str) -> Any:
    return add_equipment_line(COORDINATOR_ID, reference, {"equipment_type_id": 1, "quantity": 1})


def _update_a_line(reference: str) -> Any:
    return update_equipment_line(COORDINATOR_ID, reference, UNKNOWN_LINE_ID, {"quantity": 1})


def _remove_a_line(reference: str) -> Any:
    return remove_equipment_line(COORDINATOR_ID, reference, UNKNOWN_LINE_ID)


def _reassign(reference: str) -> Any:
    payload = {"coordinator_email": COORDINATOR_NINE_EMAIL}
    return reassign_coordinator(COORDINATOR_ID, reference, payload)


#: Every way internal staff can act on a request by its reference (ADR-0019, ADR-0021).
STAFF_OPERATIONS = [
    _list_as_technical_support,
    _list_as_coordinator,
    _add_a_line,
    _update_a_line,
    _remove_a_line,
    _reassign,
]


@pytest.fixture()
def draft_assigned_to_a_coordinator(
    saved_users: list[User], make_event_request: MakeEventRequest, save: Callable[..., None]
) -> EventRequest:
    """``DRAFT_REFERENCE``, a draft nominally assigned to coordinator 3.

    Only its status hides it from staff (AC4): if the coordinator check ran first,
    coordinator 3 would still reach it.
    """
    draft = make_event_request(
        reference=DRAFT_REFERENCE, status=EventRequestStatus.DRAFT, coordinator_id=COORDINATOR_ID
    )
    save(draft)
    return draft


@pytest.mark.parametrize(
    "operation",
    STAFF_OPERATIONS,
    ids=[operation.__name__.strip("_") for operation in STAFF_OPERATIONS],
)
def test_internal_staff_cannot_reach_a_draft_by_its_reference(
    draft_assigned_to_a_coordinator: EventRequest, operation: Callable[[str], Any]
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        operation(DRAFT_REFERENCE)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE


def test_reassigning_a_draft_changes_nothing(
    draft_assigned_to_a_coordinator: EventRequest,
    coordinator_of: Callable[[int], int | None],
    history_of: Callable[[int], list[tuple[Any, ...]]],
) -> None:
    with pytest.raises(NotFoundError):
        _reassign(DRAFT_REFERENCE)

    assert coordinator_of(draft_assigned_to_a_coordinator.id) == COORDINATOR_ID
    assert history_of(draft_assigned_to_a_coordinator.id) == []
