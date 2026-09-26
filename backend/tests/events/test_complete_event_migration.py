"""Unit tests for migration 0016, which adds SCRUM-68's history kind (ADR-0027).

``event_history_entry_kind`` gains ``event_completed``, written when the assigned
coordinator marks an event completed (AC5). No table changes and no notification
kind: the ``completed`` status itself dates from migration 0006. ``flask db check``
doesn't compare enum members, so these tests check the migration's value lists
against the model and the earlier migrations, and render its SQL for Postgres
offline so the upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import EventHistoryKind

pytestmark = pytest.mark.scrum_68

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0016_add_event_completed_history_kind.py"
#: Migration 0010 created ``event_history_entry_kind``; 0012 and 0015 added to it.
ASSIGNMENT_MIGRATION = "0010_add_coordinator_assignment_and_event_history.py"
REASSIGNMENT_MIGRATION = "0012_add_reassignment_history_kind.py"
NOTES_MIGRATION = "0015_add_event_notes_and_change_kinds.py"


def test_the_previous_history_kinds_are_what_exists_after_migration_0015(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    after_0015 = (
        set(load_migration(ASSIGNMENT_MIGRATION).HISTORY_KIND_VALUES)
        | set(load_migration(REASSIGNMENT_MIGRATION).ADDED_HISTORY_KIND_VALUES)
        | set(load_migration(NOTES_MIGRATION).ADDED_HISTORY_KIND_VALUES)
    )

    assert set(migration.PREVIOUS_HISTORY_KIND_VALUES) == after_0015


def test_migration_and_model_agree_on_the_history_kinds(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)
    previous = set(migration.PREVIOUS_HISTORY_KIND_VALUES)
    added = set(migration.ADDED_HISTORY_KIND_VALUES)

    # Subset, not equality: a later migration could add a further history kind
    # this one doesn't know about, as 0012 and 0015 later did to 0010.
    assert previous | added <= {kind.value for kind in EventHistoryKind}
    assert previous.isdisjoint(added)


def test_upgrade_adds_the_history_kind_outside_the_transaction(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    history_kind = "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS 'event_completed'"
    # Postgres won't let a transaction use an enum value it added, so the addition sits
    # between a COMMIT and a new BEGIN.
    assert sql.index("COMMIT") < sql.index(history_kind) < sql.index("BEGIN")
    assert "notification_kind" not in sql
    assert "ALTER TABLE" not in sql


def test_downgrade_deletes_the_completions_and_rebuilds_the_type_without_the_new_kind(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM event_history_entries WHERE kind = 'event_completed'",
        "ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old",
        "CREATE TYPE event_history_entry_kind AS ENUM "
        "('coordinator_assigned', 'coordinator_reassigned', 'field_changed')",
        "ALTER TABLE event_history_entries ALTER COLUMN kind "
        "TYPE event_history_entry_kind USING kind::text::event_history_entry_kind",
        "DROP TYPE event_history_entry_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert "notification_kind" not in sql
