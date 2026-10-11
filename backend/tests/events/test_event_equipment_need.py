"""Unit tests for what equipment asks of an event (SCRUM-45 AC3, AC4).

The equipment module needs an event's exact period, as UTC instants, and how many of
each equipment type it asks for. It gets them from ``get_event_equipment_need`` rather
than from the event models. Event times are wall-clock business time (ADR-0002), so
the conversion to UTC is checked with concrete values. When a reader asks, as
``get_event_equipment_need_for_viewer``, the event is scoped as its equipment lines are
(ADR-0019, ADR-0037): Technical Support see any event, a coordinator only their own.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timezone

import pytest
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.auth.permissions import Role
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import EventEquipmentLine, EventRequest, EventRequestStatus
from app.modules.events.services import (
    EventPeriodIncompleteError,
    _event_period,
    get_event_equipment_need,
    get_event_equipment_need_for_viewer,
)

pytestmark = pytest.mark.scrum_45

MakeEventRequest = Callable[..., EventRequest]
MakeEquipmentLine = Callable[..., EventEquipmentLine]
Save = Callable[..., None]

REFERENCE = "EVR-AAAAAAAA"
#: ``saved_event_request`` is assigned to coordinator 3.
ASSIGNED_COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9
TECHNICAL_SUPPORT_ID = 5


def test_the_period_is_the_events_business_time_in_utc(
    db_session: Session, saved_event_request: EventRequest
) -> None:
    # 09:00 to 17:00 in Singapore (UTC+8) is 01:00 to 09:00 UTC.
    need = get_event_equipment_need(REFERENCE, session=db_session)

    assert need.starts_at == datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
    assert need.ends_at == datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)


def test_an_event_running_past_midnight_ends_on_its_end_date(
    db_session: Session, saved_event_request: EventRequest, save: Save
) -> None:
    saved_event_request.end_date = date(2026, 10, 16)
    saved_event_request.end_time = time(2, 0)
    save(saved_event_request)

    need = get_event_equipment_need(REFERENCE, session=db_session)

    assert need.ends_at == datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)


def test_the_requested_quantity_is_listed_per_equipment_type(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Save,
) -> None:
    save(
        make_equipment_line(saved_event_request, equipment_type, quantity=2),
        make_equipment_line(saved_event_request, microphone, quantity=5),
    )

    need = get_event_equipment_need(REFERENCE, session=db_session)

    assert need.requested == {equipment_type.id: 2, microphone.id: 5}


def test_only_the_events_own_lines_are_counted(
    db_session: Session,
    saved_event_request: EventRequest,
    make_event_request: MakeEventRequest,
    make_equipment_line: MakeEquipmentLine,
    equipment_type: EquipmentType,
    save: Save,
) -> None:
    other_event = make_event_request(reference="EVR-BBBBBBBB")
    save(other_event)
    save(
        make_equipment_line(saved_event_request, equipment_type, quantity=2),
        make_equipment_line(other_event, equipment_type, quantity=7),
    )

    need = get_event_equipment_need(REFERENCE, session=db_session)

    assert need.requested == {equipment_type.id: 2}


def test_an_event_with_no_lines_requests_nothing(
    db_session: Session, saved_event_request: EventRequest
) -> None:
    assert get_event_equipment_need(REFERENCE, session=db_session).requested == {}


def test_an_unknown_reference_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        get_event_equipment_need("EVR-ZZZZZZZZ", session=db_session)


def test_a_draft_is_not_found(
    db_session: Session, make_event_request: MakeEventRequest, save: Save
) -> None:
    save(make_event_request(status=EventRequestStatus.DRAFT))

    with pytest.raises(NotFoundError):
        get_event_equipment_need(REFERENCE, session=db_session)


@pytest.mark.parametrize("missing", ["proposed_date", "end_date", "start_time", "end_time"])
def test_an_event_missing_a_date_or_time_has_no_period(
    make_event_request: MakeEventRequest, missing: str
) -> None:
    # The database refuses this for a submitted event, so build it in memory.
    event_request = make_event_request()
    setattr(event_request, missing, None)

    with pytest.raises(EventPeriodIncompleteError):
        _event_period(event_request)


# --------------------------------------------------------------------------
# ADR-0019, ADR-0037 — who may read an event's equipment need
# --------------------------------------------------------------------------


def test_the_assigned_coordinator_gets_their_events_need(
    db_session: Session, saved_event_request: EventRequest
) -> None:
    need = get_event_equipment_need_for_viewer(
        ASSIGNED_COORDINATOR_ID, REFERENCE, viewer_role=Role.EVENT_COORDINATOR, session=db_session
    )

    assert need.event_id == saved_event_request.id


@pytest.mark.parametrize("coordinator_id", [None, ASSIGNED_COORDINATOR_ID])
def test_technical_support_get_any_events_need(
    db_session: Session,
    make_event_request: MakeEventRequest,
    save: Save,
    coordinator_id: int | None,
) -> None:
    event_request = make_event_request(coordinator_id=coordinator_id)
    save(event_request)

    need = get_event_equipment_need_for_viewer(
        TECHNICAL_SUPPORT_ID,
        REFERENCE,
        viewer_role=Role.TECHNICAL_SUPPORT_STAFF,
        session=db_session,
    )

    assert need.event_id == event_request.id


@pytest.mark.parametrize(
    ("coordinator_id", "assigned_to"),
    [
        pytest.param(OTHER_COORDINATOR_ID, ASSIGNED_COORDINATOR_ID, id="another-coordinators"),
        pytest.param(ASSIGNED_COORDINATOR_ID, None, id="unassigned"),
    ],
)
def test_a_coordinator_is_told_an_event_not_assigned_to_them_does_not_exist(
    db_session: Session,
    make_event_request: MakeEventRequest,
    save: Save,
    coordinator_id: int,
    assigned_to: int | None,
) -> None:
    save(make_event_request(coordinator_id=assigned_to))

    with pytest.raises(NotFoundError) as exc_info:
        get_event_equipment_need_for_viewer(
            coordinator_id, REFERENCE, viewer_role=Role.EVENT_COORDINATOR, session=db_session
        )

    # The same answer as a reference that doesn't exist (ADR-0012, ADR-0034).
    assert exc_info.value.message == "Event request not found."


def test_technical_support_are_not_shown_a_draft(
    db_session: Session, make_event_request: MakeEventRequest, save: Save
) -> None:
    save(make_event_request(status=EventRequestStatus.DRAFT))

    with pytest.raises(NotFoundError):
        get_event_equipment_need_for_viewer(
            TECHNICAL_SUPPORT_ID,
            REFERENCE,
            viewer_role=Role.TECHNICAL_SUPPORT_STAFF,
            session=db_session,
        )
