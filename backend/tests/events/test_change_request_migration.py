"""Unit tests for migration 0053, SCRUM-56's change requests (ADR-0126).

The migration creates ``event_change_requests`` with its ``event_change_request_status``
enum and the partial unique index that keeps one Pending request per event (AC7), and
adds ``change_request_raised`` and ``change_request_withdrawn`` to ``notification_kind``
(AC5, AC8). ``flask db check`` doesn't compare enum members, so these tests check the
value lists against the models and the migration below, and render the SQL for Postgres
offline so the upgrade and the downgrade are tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.events.models import ChangeRequestStatus
from app.modules.notifications.services import NotificationKind

pytestmark = pytest.mark.scrum_56

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0053_create_event_change_requests_table.py"
#: The last migration to change ``notification_kind``. 0050, main's head when this was
#: written, changes no enum.
MIGRATION_BELOW = "0049_add_venue_booking_reconfirmed.py"
ADDED = ("change_request_raised", "change_request_withdrawn")


def test_the_previous_notification_kinds_are_what_the_migration_below_left(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(MIGRATION_BELOW)
    # In Postgres's order: each ADD VALUE appends.
    left_below = (
        *below.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *below.ADDED_NOTIFICATION_KIND_VALUES,
    )

    assert left_below == migration.PREVIOUS_NOTIFICATION_KIND_VALUES


def test_it_adds_the_models_new_kinds_and_status_and_follows_main(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    model_kinds = {kind.value for kind in NotificationKind}

    assert migration.ADDED_NOTIFICATION_KIND_VALUES == ADDED
    # Subset, not equality: a later migration may add a further kind.
    assert set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES) | set(ADDED) <= model_kinds
    assert set(ADDED).isdisjoint(migration.PREVIOUS_NOTIFICATION_KIND_VALUES)
    assert (
        tuple(status.value for status in ChangeRequestStatus)
        == migration.CHANGE_REQUEST_STATUS_VALUES
    )
    assert migration.down_revision == "0050_add_needs_reassessment"
    # ``alembic_version`` holds at most 32 characters.
    assert migration.revision == "0053_create_change_requests"
    assert len(migration.revision) <= 32


def test_with_the_kinds_added_the_type_holds_exactly_the_models_kinds(
    load_migration: LoadMigration,
) -> None:
    """The newest migration to change ``notification_kind`` leaves no kind out."""
    migration = load_migration(MIGRATION)
    notification_kinds = {
        *migration.PREVIOUS_NOTIFICATION_KIND_VALUES,
        *migration.ADDED_NOTIFICATION_KIND_VALUES,
    }

    assert notification_kinds == {kind.value for kind in NotificationKind}


def test_upgrade_creates_the_table_and_its_pending_index_then_adds_the_kinds(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert (
        "CREATE TYPE event_change_request_status AS ENUM "
        "('pending', 'approved', 'rejected', 'withdrawn')"
    ) in sql
    assert "CREATE TABLE event_change_requests" in sql
    assert "CONSTRAINT ck_event_change_requests_withdrawn_has_time" in sql
    assert (
        "CREATE INDEX ix_event_change_requests_event_request_id ON event_change_requests "
        "(event_request_id)"
    ) in sql
    assert (
        "CREATE UNIQUE INDEX uq_event_change_requests_pending ON event_change_requests "
        "(event_request_id) WHERE status = 'pending'"
    ) in sql
    # Postgres won't let a transaction use an enum value it added, so the additions sit
    # after the table, between a COMMIT and a new BEGIN.
    commit = sql.index("COMMIT")
    assert sql.index("CREATE TABLE event_change_requests") < commit
    for value in ADDED:
        added = f"ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS '{value}'"
        assert commit < sql.index(added) < sql.index("BEGIN", commit)


def test_downgrade_removes_everything_the_upgrade_added(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'change_request_raised'",
        "DELETE FROM notifications WHERE kind = 'change_request_withdrawn'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted'",
        "'replacement_venue_approved', 'venue_booking_reconfirmed')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
        "DROP INDEX uq_event_change_requests_pending",
        "DROP INDEX ix_event_change_requests_event_request_id",
        "DROP TABLE event_change_requests",
        "DROP TYPE event_change_request_status",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert "'change_request_raised')" not in sql
