"""Service tests for SCRUM-24 "see the events my role is involved in".

AC2: an Event Coordinator sees the submitted requests no coordinator has yet, as a
list separate from their own assigned one (``test_list_assigned_requests.py``).
Later commits add AC4 (the events with an equipment request) and AC7 (a coordinator
reading an event record).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import list_unassigned_event_requests

pytestmark = pytest.mark.scrum_24

MakeEventRequest = Callable[..., EventRequest]
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
