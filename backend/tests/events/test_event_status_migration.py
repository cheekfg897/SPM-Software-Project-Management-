"""Unit tests for migration 0006, which adds SCRUM-22's event request statuses.

``flask db check`` doesn't compare enum members, so these tests check the migration's
value list against the model. They also render the migration's SQL for Postgres
offline, so the upgrade and the downgrade are tested without a database (ADR-0012).
"""

from __future__ import annotations

import importlib.util
import io
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from app.modules.events.models import EventRequestStatus

pytestmark = pytest.mark.scrum_22

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "0006_add_event_request_statuses.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0006", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render(operation: Callable[[], None]) -> str:
    """The SQL Alembic would run for ``operation`` on Postgres, rendered offline."""
    buffer = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": buffer, "literal_binds": True},
    )
    with Operations.context(context):
        operation()
    return buffer.getvalue()


def test_migration_and_model_agree_on_the_status_values() -> None:
    migration = _load_migration()
    previous = set(migration.PREVIOUS_STATUS_VALUES)
    added = set(migration.ADDED_STATUS_VALUES)

    assert previous | added == {status.value for status in EventRequestStatus}
    assert previous.isdisjoint(added)


def test_upgrade_adds_each_new_value_outside_the_transaction() -> None:
    migration = _load_migration()

    sql = _render(migration.upgrade)

    for value in ["draft", "under_review", "confirmed", "completed", "cancelled", "rejected"]:
        assert f"ALTER TYPE event_request_status ADD VALUE '{value}'" in sql
    # Postgres won't let a transaction use an enum value it added, so the additions
    # sit between a COMMIT and a new BEGIN.
    assert sql.index("COMMIT") < sql.index("ADD VALUE")
    assert sql.rindex("ADD VALUE") < sql.index("BEGIN")


def test_downgrade_rebuilds_the_type_with_only_submitted() -> None:
    migration = _load_migration()
    expected_in_order = [
        "UPDATE event_requests SET status = 'submitted' WHERE status != 'submitted'",
        "ALTER TYPE event_request_status RENAME TO event_request_status_old",
        "CREATE TYPE event_request_status AS ENUM ('submitted')",
        "ALTER TABLE event_requests ALTER COLUMN status "
        "TYPE event_request_status USING status::text::event_request_status",
        "DROP TYPE event_request_status_old",
    ]

    sql = _render(migration.downgrade)

    positions = [sql.find(statement) for statement in expected_in_order]
    assert -1 not in positions
    assert positions == sorted(positions)
