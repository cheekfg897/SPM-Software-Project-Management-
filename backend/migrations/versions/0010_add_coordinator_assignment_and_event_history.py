"""Add coordinator assignment, the event history table and a notification kind.

Revision ID: 0010_add_coordinator_assignment
Revises: 0009_create_notifications
Create Date: 2026-09-25

SCRUM-30 "Assign a coordinator to a submitted event" (ADR-0018):

* ``notification_kind`` gains ``coordinator_assigned``. It is added first, outside
  the migration's transaction as 0006 does, and with ``IF NOT EXISTS`` so that if a
  later step fails the upgrade can simply be run again.
* ``event_requests.coordinator_id``, the one assigned Event Coordinator (nullable: no
  coordinator may exist, and older rows have none).
* ``event_history_entries`` with its ``event_history_entry_kind`` enum type.

Downgrading deletes every ``coordinator_assigned`` notification, since Postgres can't
remove an enum value and the type is rebuilt without it: a lossy rollback, like 0006.
Foreign keys to ``users`` and ``event_requests`` are database-level only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_add_coordinator_assignment"
down_revision = "0009_create_notifications"
branch_labels = None
depends_on = None

#: What migration 0009 created. Downgrade rebuilds the type with just this.
PREVIOUS_NOTIFICATION_KIND_VALUES = ("event_request_submitted",)

#: Added here (SCRUM-30 AC4).
ADDED_NOTIFICATION_KIND_VALUES = ("coordinator_assigned",)

#: The event history kinds so far (ADR-0018).
HISTORY_KIND_VALUES = ("coordinator_assigned",)

#: Named so batch mode can drop it, as 0007 does for ``organisation_id``.
EVENT_REQUESTS_COORDINATOR_FK = "fk_event_requests_coordinator_id"


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself, so the
    # addition runs outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_NOTIFICATION_KIND_VALUES:
            op.execute(
                sa.text("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS :value").bindparams(
                    value=value
                )
            )

    # batch mode so SQLite can drop columns too; on PostgreSQL it's plain ALTER TABLE.
    with op.batch_alter_table("event_requests") as batch_op:
        batch_op.add_column(sa.Column("coordinator_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            EVENT_REQUESTS_COORDINATOR_FK, "users", ["coordinator_id"], ["id"]
        )
        batch_op.create_index(
            batch_op.f("ix_event_requests_coordinator_id"), ["coordinator_id"], unique=False
        )

    op.create_table(
        "event_history_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_request_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind", sa.Enum(*HISTORY_KIND_VALUES, name="event_history_entry_kind"), nullable=False
        ),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["event_request_id"], ["event_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_event_history_entries_event_request_id"),
        "event_history_entries",
        ["event_request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_event_history_entries_event_request_id"), table_name="event_history_entries"
    )
    op.drop_table("event_history_entries")
    # drop_table leaves the enum type behind. Plain SQL rather than sa.Enum.drop, which
    # asks the database whether the type exists and so can't be rendered offline.
    op.execute(sa.text("DROP TYPE event_history_entry_kind"))

    with op.batch_alter_table("event_requests") as batch_op:
        batch_op.drop_index(batch_op.f("ix_event_requests_coordinator_id"))
        batch_op.drop_constraint(EVENT_REQUESTS_COORDINATOR_FK, type_="foreignkey")
        batch_op.drop_column("coordinator_id")

    # Postgres can't remove an enum value, so the type is rebuilt with the original
    # list and the column re-cast; notifications of the removed kind go first.
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    op.execute(sa.text("ALTER TYPE notification_kind RENAME TO notification_kind_old"))
    sa.Enum(*PREVIOUS_NOTIFICATION_KIND_VALUES, name="notification_kind").create(op.get_bind())
    op.execute(
        sa.text(
            "ALTER TABLE notifications ALTER COLUMN kind "
            "TYPE notification_kind USING kind::text::notification_kind"
        )
    )
    op.execute(sa.text("DROP TYPE notification_kind_old"))
