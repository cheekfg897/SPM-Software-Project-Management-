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
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)

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

    Add one to ``db_session`` to persist it. Everything but the three parameters is
    fixed; tests about the other fields go through ``submit_event_request`` with
    ``valid_event_request_payload``.
    """

    def _make(
        *,
        reference: str = "EVR-AAAAAAAA",
        status: EventRequestStatus = EventRequestStatus.SUBMITTED,
        organiser_id: int = 7,
    ) -> EventRequest:
        return EventRequest(
            reference=reference,
            status=status,
            organiser_id=organiser_id,
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
