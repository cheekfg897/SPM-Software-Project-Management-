"""Fixtures for the events module tests."""

from __future__ import annotations

import importlib.util
import io
from collections.abc import Callable
from datetime import date, time
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    CoordinatorContact,
    EventEdit,
    reassign_coordinator,
    save_draft_event_request,
    start_event_request_review,
    submit_event_request,
    update_event_request,
)
from app.modules.notifications.services import list_notifications_for_recipient
from tests.events.cases import DRAFT_REFERENCE

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "versions"


#: Every role but Event Coordinator, in a fixed order so test ids are stable.
NON_COORDINATOR_ROLES = sorted(ALL_ROLES - {Role.EVENT_COORDINATOR}, key=lambda role: role.value)


@pytest.fixture(params=NON_COORDINATOR_ROLES, ids=lambda role: role.value)
def non_coordinator_role(request: pytest.FixtureRequest) -> Role:
    """Each role but Event Coordinator in turn, for routes only coordinators call."""
    return request.param


#: Every role but Event Organiser, in a fixed order so test ids are stable.
NON_ORGANISER_ROLES = sorted(ALL_ROLES - {Role.EVENT_ORGANISER}, key=lambda role: role.value)


@pytest.fixture(params=NON_ORGANISER_ROLES, ids=lambda role: role.value)
def non_organiser_role(request: pytest.FixtureRequest) -> Role:
    """Each role but Event Organiser in turn, for routes only organisers call."""
    return request.param


@pytest.fixture()
def integrity_error() -> Callable[[Exception], IntegrityError]:
    """Wrap ``orig`` in an ``IntegrityError`` as SQLAlchemy would raise it."""

    def _make(orig: Exception) -> IntegrityError:
        return IntegrityError("INSERT INTO event_requests ...", {}, orig)

    return _make


@pytest.fixture()
def references_in_order() -> Callable[..., Callable[[], str]]:
    """Factory for a reference factory that hands out given references, in order."""

    def _factory(*values: str) -> Callable[[], str]:
        remaining = iter(values)
        return lambda: next(remaining)

    return _factory


@pytest.fixture()
def other_organisers(
    saved_users: list[User], make_user: Callable[..., User], save: Callable[..., None]
) -> list[User]:
    """Save three more organisers: 8 and 6 of organisations 3 and 4, and unlinked 10.

    Alongside organiser 7 (``saved_users``), these give tests a colleague in the same
    organisation (8), one in another organisation (6), and an account SCRUM-66 has not
    linked to any organisation yet (10).
    """
    organisers = [
        make_user(
            email="organiser8@example.com", role=Role.EVENT_ORGANISER, user_id=8, organisation_id=3
        ),
        make_user(
            email="organiser6@example.com", role=Role.EVENT_ORGANISER, user_id=6, organisation_id=4
        ),
        make_user(email="organiser10@example.com", role=Role.EVENT_ORGANISER, user_id=10),
    ]
    save(*organisers)
    return organisers


@pytest.fixture()
def coordinator_three() -> CoordinatorContact:
    """Coordinator 3 of ``saved_users``, as the organiser sees them (SCRUM-24 AC7)."""
    return CoordinatorContact(full_name="Coordinator Three", email="coordinator3@example.com")


@pytest.fixture()
def today() -> date:
    """A fixed "today" so date rules don't depend on when the tests run."""
    return date(2026, 9, 15)


@pytest.fixture()
def valid_event_request_payload() -> dict[str, Any]:
    """A submission that satisfies every rule, with every field filled in."""
    return {
        "name": "ConnectSphere Partner Summit",
        "purpose": "Annual showcase for partner organisations",
        "description": "Keynotes in the morning, breakout sessions after lunch.",
        "proposed_date": "2026-10-15",
        "start_time": "09:00",
        "end_time": "17:00",
        "expected_attendance": 250,
        "venue_requirements": "Main hall with a stage and 3 breakout rooms",
        "accessibility_needs": "Step-free access and live captioning",
        "equipment_requirements": "2 projectors, PA system, 4 wireless mics",
        "registration_required": True,
    }


@pytest.fixture()
def make_event_request() -> Callable[..., EventRequest]:
    """Factory for in-memory ``EventRequest`` objects.

    Add one to ``db_session`` to persist it. By default it is organiser 7's, filed
    under client organisation 3 as ``saved_users`` links them (SCRUM-66 AC4).
    Everything but the parameters is fixed; tests about the other fields go through
    ``submit_event_request`` with ``valid_event_request_payload``. The event ends on
    the day it starts.
    """

    def _make(
        *,
        reference: str = "EVR-AAAAAAAA",
        status: EventRequestStatus = EventRequestStatus.SUBMITTED,
        organiser_id: int = 7,
        organisation_id: int | None = 3,
        coordinator_id: int | None = None,
        proposed_date: date = date(2026, 10, 15),
        start_time: time = time(9, 0),
    ) -> EventRequest:
        return EventRequest(
            reference=reference,
            status=status,
            organiser_id=organiser_id,
            organisation_id=organisation_id,
            coordinator_id=coordinator_id,
            name="Partner Summit",
            proposed_date=proposed_date,
            end_date=proposed_date,
            start_time=start_time,
            end_time=time(17, 0),
            expected_attendance=250,
            registration_required=False,
        )

    return _make


@pytest.fixture()
def submit_valid_request(
    db_session: Session, valid_event_request_payload: dict[str, Any], today: date
) -> Callable[..., EventRequest]:
    """Submit ``valid_event_request_payload`` as organiser 7 on ``db_session``.

    Hands out the given references in order (``EVR-AAAAAAAA`` if none are given), so
    a test can force a reference collision. The payload is the fixture's own dict, so
    a test may change it before submitting.
    """

    def _submit(*references: str) -> EventRequest:
        remaining = iter(references or ("EVR-AAAAAAAA",))
        return submit_event_request(
            7,
            valid_event_request_payload,
            session=db_session,
            today=today,
            reference_factory=lambda: next(remaining),
        )

    return _submit


@pytest.fixture()
def history_of(
    db_session: Session,
) -> Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]:
    """The saved history of an event request, oldest first (ADR-0018).

    Each entry as ``(kind, actor_id, details)``, read back from the database.
    """

    def _history(
        event_request_id: int,
    ) -> list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]:
        db_session.expire_all()
        stmt = (
            select(EventHistoryEntry)
            .where(EventHistoryEntry.event_request_id == event_request_id)
            .order_by(EventHistoryEntry.occurred_at, EventHistoryEntry.id)
        )
        entries = []
        for entry in db_session.scalars(stmt):
            entries.append((entry.kind, entry.actor_id, entry.details))
        return entries

    return _history


@pytest.fixture()
def coordinator_of(db_session: Session) -> Callable[[int], int | None]:
    """The coordinator a saved request is assigned to, read back from the database."""

    def _coordinator_of(event_request_id: int) -> int | None:
        db_session.expire_all()
        event_request = db_session.get(EventRequest, event_request_id)
        assert event_request is not None
        return event_request.coordinator_id

    return _coordinator_of


@pytest.fixture()
def organiser_is_found(mock_session: MagicMock, make_user: Callable[..., User]) -> None:
    """Make ``mock_session`` find organiser 7, linked to client organisation 3.

    Submitting looks up the organiser to copy their organisation (SCRUM-66 AC4).
    """
    mock_session.get.return_value = make_user(
        role=Role.EVENT_ORGANISER, user_id=7, organisation_id=3
    )


@pytest.fixture()
def load_migration() -> Callable[[str], ModuleType]:
    """Import a migration file from ``migrations/versions`` by its file name."""

    def _load(file_name: str) -> ModuleType:
        spec = importlib.util.spec_from_file_location(
            f"migration_{file_name[:4]}", MIGRATIONS_DIR / file_name
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return _load


@pytest.fixture()
def render_migration_sql() -> Callable[[Callable[[], None]], str]:
    """Render the SQL Alembic would run on Postgres for a migration step, offline.

    ``flask db check`` doesn't compare enum members, and the unit suite has no
    Postgres, so migration tests read the SQL instead.
    """

    def _render(operation: Callable[[], None]) -> str:
        buffer = io.StringIO()
        context = MigrationContext.configure(
            dialect_name="postgresql",
            opts={"as_sql": True, "output_buffer": buffer, "literal_binds": True},
        )
        with Operations.context(context):
            operation()
        return buffer.getvalue()

    return _render


@pytest.fixture()
def assert_in_order() -> Callable[[str, list[str]], None]:
    """Check that every statement appears in rendered SQL, in the given order."""

    def _assert(sql: str, expected_in_order: list[str]) -> None:
        positions = [sql.find(statement) for statement in expected_in_order]
        assert -1 not in positions
        assert positions == sorted(positions)

    return _assert


@pytest.fixture()
def notifications_of() -> Callable[[int], list[tuple[Any, ...]]]:
    """A user's notifications, newest first, as rows of what each one records.

    Each row is (event request id, reference, name, kind, read at).
    """

    def _notifications_of(user_id: int) -> list[tuple[Any, ...]]:
        rows = []
        for notification in list_notifications_for_recipient(user_id):
            rows.append(
                (
                    notification.event_request_id,
                    notification.event_reference,
                    notification.event_name,
                    notification.kind,
                    notification.read_at,
                )
            )
        return rows

    return _notifications_of


@pytest.fixture()
def saved_event_request(
    make_event_request: Callable[..., EventRequest], save: Callable[..., None]
) -> EventRequest:
    """Event request ``EVR-AAAAAAAA`` by organiser 7, ``submitted`` and saved.

    It is assigned to Event Coordinator 3, who may change its equipment (ADR-0019).
    """
    event_request = make_event_request(coordinator_id=3)
    save(event_request)
    return event_request


@pytest.fixture()
def save_draft(db_session: Session) -> Callable[[int, dict[str, Any]], EventRequest]:
    """Save a draft through the service, always under ``DRAFT_REFERENCE`` (SCRUM-20).

    Runs on ``db_session``, so the draft is really persisted and can be read back or
    reopened by another service call in the same test.
    """

    def _save(organiser_id: int, payload: dict[str, Any]) -> EventRequest:
        return save_draft_event_request(
            organiser_id, payload, session=db_session, reference_factory=lambda: DRAFT_REFERENCE
        )

    return _save


@pytest.fixture()
def reload_event_request(db_session: Session) -> Callable[[int], EventRequest]:
    """Read an event request back from the database rather than the session's cache."""

    def _reload(event_request_id: int) -> EventRequest:
        db_session.expire_all()
        event_request = db_session.get(EventRequest, event_request_id)
        assert event_request is not None
        return event_request

    return _reload


@pytest.fixture()
def set_status(
    saved_event_request: EventRequest, save: Callable[..., None]
) -> Callable[[EventRequestStatus], None]:
    """Move ``saved_event_request`` to another status and save it."""

    def _set(status: EventRequestStatus) -> None:
        saved_event_request.status = status
        save(saved_event_request)

    return _set


@pytest.fixture()
def valid_equipment_line_payload(equipment_type: EquipmentType) -> dict[str, Any]:
    """An equipment line body that satisfies every rule: two of the saved type."""
    return {"equipment_type_id": equipment_type.id, "quantity": 2, "notes": "Needs HDMI"}


@pytest.fixture()
def microphone(
    make_equipment_type: Callable[..., EquipmentType], save: Callable[..., None]
) -> EquipmentType:
    """A second saved equipment type, for events that need more than one."""
    saved = make_equipment_type(name="Microphone", total_quantity=20)
    save(saved)
    return saved


@pytest.fixture()
def make_equipment_line() -> Callable[..., EventEquipmentLine]:
    """Factory for ``EventEquipmentLine`` objects; add one to ``db_session`` to save."""

    def _make(
        event_request: EventRequest,
        equipment_type: EquipmentType,
        *,
        quantity: int = 2,
        notes: str | None = "Needs HDMI",
    ) -> EventEquipmentLine:
        return EventEquipmentLine(
            event_request_id=event_request.id,
            equipment_type_id=equipment_type.id,
            quantity=quantity,
            notes=notes,
            status=EquipmentLineStatus.REQUESTED,
        )

    return _make


@pytest.fixture()
def event_needing(
    make_event_request: Callable[..., EventRequest],
    make_equipment_line: Callable[..., EventEquipmentLine],
    equipment_type: EquipmentType,
    save: Callable[..., None],
) -> Callable[..., EventRequest]:
    """Factory: save an event that needs two of ``equipment_type`` (a projector)."""

    def _save(
        reference: str = "EVR-AAAAAAAA",
        *,
        proposed_date: date = date(2026, 10, 15),
        status: EventRequestStatus = EventRequestStatus.SUBMITTED,
    ) -> EventRequest:
        event_request = make_event_request(
            reference=reference, proposed_date=proposed_date, status=status
        )
        save(event_request)
        save(make_equipment_line(event_request, equipment_type))
        return event_request

    return _save


@pytest.fixture()
def shown_event(make_event_request: Callable[..., EventRequest]) -> EventRequest:
    """The in-memory event request that the API shows as ``event_as_shown``."""
    return make_event_request()


@pytest.fixture()
def event_as_shown() -> dict[str, Any]:
    """``shown_event`` as the equipment routes show it (ADR-0019).

    The same field names and formats as the event request itself.
    """
    return {
        "reference": "EVR-AAAAAAAA",
        "name": "Partner Summit",
        "proposed_date": "2026-10-15",
        "end_date": "2026-10-15",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
    }


@pytest.fixture()
def shown_line(
    shown_event: EventRequest,
    make_equipment_type: Callable[..., EquipmentType],
    make_equipment_line: Callable[..., EventEquipmentLine],
) -> EventEquipmentLine:
    """An in-memory line of ``shown_event`` that the API shows as ``line_as_shown``."""
    line = make_equipment_line(shown_event, make_equipment_type())
    # In-memory objects have no ids, so set the ones ``line_as_shown`` expects.
    line.id = 7
    line.equipment_type_id = 1
    return line


@pytest.fixture()
def line_as_shown() -> dict[str, Any]:
    """``shown_line`` as the API shows it (SCRUM-37 AC4)."""
    return {
        "id": 7,
        "equipment_type_id": 1,
        "quantity": 2,
        "notes": "Needs HDMI",
        "status": "requested",
    }


@pytest.fixture()
def reload_equipment_line(db_session: Session) -> Callable[[int], EventEquipmentLine]:
    """Read an equipment line back from the database rather than the session's cache."""

    def _reload(line_id: int) -> EventEquipmentLine:
        db_session.expire_all()
        line = db_session.get(EventEquipmentLine, line_id)
        assert line is not None
        return line

    return _reload


@pytest.fixture()
def edit_event(
    saved_users: list[User], saved_event_request: EventRequest, today: date
) -> Callable[[int, dict[str, Any] | None], EventEdit]:
    """Edit ``saved_event_request`` (``EVR-AAAAAAAA``) as ``actor_id`` (SCRUM-33).

    Runs against the default session, which ``db_session`` also yields, so a test can
    read back what was saved through either fixture.
    """

    def _edit(actor_id: int, payload: dict[str, Any] | None) -> EventEdit:
        return update_event_request(actor_id, "EVR-AAAAAAAA", payload, today=today)

    return _edit


@pytest.fixture()
def reassign(
    saved_users: list[User], saved_event_request: EventRequest
) -> Callable[[int, str], tuple[EventRequest, CoordinatorContact]]:
    """Reassign ``saved_event_request`` to the user with this email (SCRUM-87).

    The request, ``EVR-AAAAAAAA``, starts with Event Coordinator 3; ``actor_id`` is
    who reassigns it. Runs on ``db_session`` with ``saved_users``.
    """

    def _reassign(actor_id: int, coordinator_email: str) -> tuple[EventRequest, CoordinatorContact]:
        payload = {"coordinator_email": coordinator_email}
        return reassign_coordinator(actor_id, "EVR-AAAAAAAA", payload)

    return _reassign


@pytest.fixture()
def reassignment_lookups(
    mock_session: MagicMock,
    make_event_request: Callable[..., EventRequest],
    make_user: Callable[..., User],
) -> EventRequest:
    """Make ``mock_session`` find what a reassignment from coordinator 3 to 9 looks up.

    The request ``EVR-AAAAAAAA`` (id 1, with coordinator 3) by its reference, then
    coordinator 9 by email; either coordinator by id, for their name and email.
    Returns the request.
    """
    event_request = make_event_request(coordinator_id=3)
    event_request.id = 1
    coordinators = {}
    for user_id, name in [(3, "Three"), (9, "Nine")]:
        coordinators[user_id] = make_user(
            email=f"coordinator{user_id}@example.com",
            full_name=f"Coordinator {name}",
            role=Role.EVENT_COORDINATOR,
            user_id=user_id,
        )

    def get_coordinator(_model: type, user_id: int) -> User:
        return coordinators[user_id]

    mock_session.scalar.side_effect = [event_request, coordinators[9]]
    mock_session.get.side_effect = get_coordinator
    return event_request


@pytest.fixture()
def start_review(
    saved_users: list[User], saved_event_request: EventRequest
) -> Callable[[int], EventRequest]:
    """Move ``saved_event_request`` to under review as ``actor_id`` (SCRUM-31).

    The request, ``EVR-AAAAAAAA``, is submitted and assigned to Event Coordinator 3.
    Runs on ``db_session`` with ``saved_users``.
    """

    def _start(actor_id: int) -> EventRequest:
        return start_event_request_review(actor_id, "EVR-AAAAAAAA")

    return _start
