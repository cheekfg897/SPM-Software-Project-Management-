"""Unit tests for SCRUM-56 "Request a change after submitting my event": the record.

AC4: the change request appears on the event record with its status, Pending when
raised and Withdrawn once withdrawn (AC8), with the note when the event's cancellation
withdrew it (AC9). Each one shows what should change (each field with the value it
had when raised and the value asked for), why, who raised it and when, oldest first.
Both the Organiser's and the coordinator's record show them (ADR-0126); no user id
appears.

The service tests run against ``db_session`` with ``saved_users``; the change requests
are written directly with ``save_change_request`` so their times can be pinned.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import ChangeRequestStatus, EventChangeRequest, EventRequest
from app.modules.events.services import (
    ChangeRequestAsShown,
    CoordinatorEventRecord,
    EventRecord,
    OrganiserEventRecord,
    RequestedChange,
)

pytestmark = pytest.mark.scrum_56

OpenRecord = Callable[[], EventRecord]
OpenRecordRoute = Callable[[OrganiserEventRecord], dict[str, Any]]
SaveChangeRequest = Callable[..., EventChangeRequest]
CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

ORGANISER_NAME = "Alice Example"
REASON = "More partners are coming."
EARLIER = datetime(2026, 9, 14, 1, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)
WITHDRAWN_AT = datetime(2026, 9, 16, 2, 30, tzinfo=timezone.utc)
MORE_ATTENDEES = (RequestedChange("expected_attendance", 250, 300),)

PENDING_AS_SHOWN = ChangeRequestAsShown(
    id=2,
    status=ChangeRequestStatus.PENDING,
    changes=(
        RequestedChange("proposed_date", "2026-10-15", "2026-10-20"),
        RequestedChange("expected_attendance", 250, 300),
    ),
    reason=REASON,
    raised_by=ORGANISER_NAME,
    raised_at=LATER,
    withdrawn_at=None,
    withdrawal_note=None,
)
WITHDRAWN_AS_SHOWN = ChangeRequestAsShown(
    id=1,
    status=ChangeRequestStatus.WITHDRAWN,
    changes=MORE_ATTENDEES,
    reason=REASON,
    raised_by=ORGANISER_NAME,
    raised_at=EARLIER,
    withdrawn_at=WITHDRAWN_AT,
    withdrawal_note="Withdrawn because the event was cancelled.",
)
#: The two above as the record route sends them, in business time (ADR-0009).
WITHDRAWN_BODY = {
    "id": 1,
    "status": "withdrawn",
    "changes": [
        {"field": "expected_attendance", "previous_value": 250, "requested_value": 300},
    ],
    "reason": REASON,
    "raised_by": ORGANISER_NAME,
    "raised_at": "2026-09-14T09:00:00+08:00",
    "withdrawn_at": "2026-09-16T10:30:00+08:00",
    "withdrawal_note": "Withdrawn because the event was cancelled.",
}
PENDING_BODY = {
    "id": 2,
    "status": "pending",
    "changes": [
        {"field": "proposed_date", "previous_value": "2026-10-15", "requested_value": "2026-10-20"},
        {"field": "expected_attendance", "previous_value": 250, "requested_value": 300},
    ],
    "reason": REASON,
    "raised_by": ORGANISER_NAME,
    "raised_at": "2026-09-15T09:00:00+08:00",
    "withdrawn_at": None,
    "withdrawal_note": None,
}


# --------------------------------------------------------------------------
# AC4 — the record shows each change request with its status
# --------------------------------------------------------------------------


def test_the_record_shows_each_change_request_oldest_first(
    open_record: OpenRecord,
    saved_event_request: EventRequest,
    save_change_request: SaveChangeRequest,
    save: Callable[..., None],
) -> None:
    # Saved newest first, so only the times can put them in the order raised.
    later = save_change_request(saved_event_request, raised_at=LATER)
    later.requested_values = {"proposed_date": "2026-10-20", "expected_attendance": 300}
    later.previous_values = {"proposed_date": "2026-10-15", "expected_attendance": 250}
    save(later)
    earlier = save_change_request(
        saved_event_request, ChangeRequestStatus.WITHDRAWN, raised_at=EARLIER
    )
    earlier.withdrawn_at = WITHDRAWN_AT
    save(earlier)

    record = open_record()

    assert record.change_requests == (
        ChangeRequestAsShown(
            id=earlier.id,
            status=ChangeRequestStatus.WITHDRAWN,
            changes=MORE_ATTENDEES,
            reason=REASON,
            raised_by=ORGANISER_NAME,
            raised_at=EARLIER,
            withdrawn_at=WITHDRAWN_AT,
            withdrawal_note=None,
        ),
        ChangeRequestAsShown(
            id=later.id,
            status=ChangeRequestStatus.PENDING,
            changes=PENDING_AS_SHOWN.changes,
            reason=REASON,
            raised_by=ORGANISER_NAME,
            raised_at=LATER,
            withdrawn_at=None,
            withdrawal_note=None,
        ),
    )


def test_an_event_with_no_change_request_shows_none(
    open_record: OpenRecord, saved_event_request: EventRequest
) -> None:
    record = open_record()

    assert record.change_requests == ()


def test_another_events_change_request_is_not_shown(
    open_record: OpenRecord,
    saved_event_request: EventRequest,
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
    save_change_request: SaveChangeRequest,
) -> None:
    other_event = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=3)
    save(other_event)
    save_change_request(other_event)

    record = open_record()

    assert record.change_requests == ()


def test_a_removed_organisers_name_is_null(
    open_record: OpenRecord,
    saved_event_request: EventRequest,
    save_change_request: SaveChangeRequest,
    save: Callable[..., None],
) -> None:
    change_request = save_change_request(saved_event_request)
    change_request.requested_by = 99
    save(change_request)

    record = open_record()

    [shown] = record.change_requests
    assert shown.raised_by is None


# --------------------------------------------------------------------------
# AC4 — the record route shows them as ``change_requests``
# --------------------------------------------------------------------------


def test_the_organisers_record_route_shows_them_in_business_time(
    open_record_route: OpenRecordRoute, make_event_request: Callable[..., EventRequest]
) -> None:
    record = OrganiserEventRecord(
        event_request=make_event_request(),
        coordinator=None,
        change_requests=(WITHDRAWN_AS_SHOWN, PENDING_AS_SHOWN),
    )

    body = open_record_route(record)

    assert body["change_requests"] == [WITHDRAWN_BODY, PENDING_BODY]


def test_the_coordinators_record_route_shows_them_too(
    call_route: CallRoute,
    replace_services: ReplaceServices,
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    make_event_request: Callable[..., EventRequest],
) -> None:
    record = CoordinatorEventRecord(
        event_request=make_event_request(coordinator_id=3),
        coordinator=None,
        change_requests=(PENDING_AS_SHOWN,),
    )
    replace_services(routes, {"get_event_record_for_coordinator": record})
    token = token_for(make_user(role=Role.EVENT_COORDINATOR, user_id=3))

    response, status = call_route(
        "events.get_my_request",
        "GET",
        "/api/events/requests/EVR-AAAAAAAA",
        {"reference": "EVR-AAAAAAAA"},
        token,
    )

    assert status == 200
    assert response.get_json()["change_requests"] == [PENDING_BODY]
