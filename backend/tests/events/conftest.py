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
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import submit_event_request
from app.modules.notifications.services import list_notifications_for_recipient

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "versions"


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

    Add one to ``db_session`` to persist it. Everything but the four parameters is
    fixed; tests about the other fields go through ``submit_event_request`` with
    ``valid_event_request_payload``.
    """

    def _make(
        *,
        reference: str = "EVR-AAAAAAAA",
        status: EventRequestStatus = EventRequestStatus.SUBMITTED,
        organiser_id: int = 7,
        coordinator_id: int | None = None,
    ) -> EventRequest:
        return EventRequest(
            reference=reference,
            status=status,
            organiser_id=organiser_id,
            coordinator_id=coordinator_id,
            name="Partner Summit",
            proposed_date=date(2026, 10, 15),
            end_date=date(2026, 10, 15),
            start_time=time(9, 0),
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
    """Event request ``EVR-AAAAAAAA`` by organiser 7, ``submitted`` and saved."""
    event_request = make_event_request()
    save(event_request)
    return event_request


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
def reload_equipment_line(db_session: Session) -> Callable[[int], EventEquipmentLine]:
    """Read an equipment line back from the database rather than the session's cache."""

    def _reload(line_id: int) -> EventEquipmentLine:
        db_session.expire_all()
        line = db_session.get(EventEquipmentLine, line_id)
        assert line is not None
        return line

    return _reload
