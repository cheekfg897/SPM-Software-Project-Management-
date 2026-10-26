"""Unit tests for migration 0048, which creates SCRUM-89's ``revoked_tokens`` table.

A row is one logged-out access token: its ``jti``, whose token it was, and when the
token expires (ADR-0110). The database keeps each ``jti`` once, whatever the service
checks. The model-level test runs that constraint for real on SQLite; the migration's
SQL is rendered for Postgres offline, so the upgrade and the downgrade are tested
without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from types import ModuleType

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models import RevokedToken, User

pytestmark = pytest.mark.scrum_89

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0048_create_revoked_tokens_table.py"
EXPIRES_AT = datetime(2026, 10, 26, 13, 0, tzinfo=timezone.utc)


def test_the_database_keeps_each_jti_once(
    saved_users: list[User], save: Callable[..., None]
) -> None:
    save(RevokedToken(jti="the-same-jti", user_id=7, expires_at=EXPIRES_AT))

    with pytest.raises(IntegrityError, match=r"revoked_tokens\.jti"):
        save(RevokedToken(jti="the-same-jti", user_id=3, expires_at=EXPIRES_AT))


def test_the_migration_follows_0047(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert (migration.revision, migration.down_revision) == (
        "0048_create_revoked_tokens",
        "0047_add_replacement_approved",
    )


def test_upgrade_creates_the_table_with_its_columns_and_rules(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert "CREATE TABLE revoked_tokens" in sql
    for column in [
        "jti VARCHAR(36) NOT NULL",
        "user_id INTEGER NOT NULL",
        "expires_at TIMESTAMP WITH TIME ZONE NOT NULL",
    ]:
        assert column in sql
    assert "FOREIGN KEY(user_id) REFERENCES users (id)" in sql
    assert "CONSTRAINT uq_revoked_tokens_jti UNIQUE (jti)" in sql


def test_upgrade_indexes_the_expiry_each_logout_deletes_by(
    load_migration: LoadMigration, render_migration_sql: RenderMigrationSql
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.upgrade)

    assert "CREATE INDEX ix_revoked_tokens_expires_at ON revoked_tokens (expires_at)" in sql


def test_downgrade_drops_the_index_before_the_table(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, ["DROP INDEX ix_revoked_tokens_expires_at", "DROP TABLE revoked_tokens"])
