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
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import (
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    get_event_record_for_organiser,
    get_event_request_for_organiser,
    list_event_requests_for_organiser,
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
