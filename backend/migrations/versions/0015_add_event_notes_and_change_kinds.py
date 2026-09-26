"""Add event notes columns and the field_changed / significant_change enum values.

Revision ID: 0015_add_event_notes_changes
Revises: 0014_allow_incomplete_drafts
Create Date: 2026-09-26

SCRUM-33 "Update event information and flag significant changes" (ADR-0025):

* ``event_requests`` gains ``programme_notes`` and ``internal_planning_notes``, both
  nullable ``Text`` columns an assigned coordinator can edit (AC1);
  ``internal_planning_notes`` is never shown to organisers.
* ``event_history_entry_kind`` gains ``field_changed``, one entry per changed field
  when a coordinator edits a request (AC2, AC4).
* ``notification_kind`` gains ``significant_change``, raised to Technical Support
  Staff when a significant change affects an event's equipment arrangements (AC2).

Both enum values are added outside the migration's transaction, with
``IF NOT EXISTS``, as 0010 and 0012 do. Downgrading deletes the rows of each new kind
and rebuilds both enum types without them (lossy, like 0010-0012's), then drops the
two new columns.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0015_add_event_notes_changes"
down_revision = "0014_allow_incomplete_drafts"
branch_labels = None
depends_on = None

#: What migrations 0010 and 0012 created. Downgrade rebuilds
#: ``event_history_entry_kind`` with just this.
PREVIOUS_HISTORY_KIND_VALUES = ("coordinator_assigned", "coordinator_reassigned")

#: Added here (SCRUM-33 AC2, AC4).
ADDED_HISTORY_KIND_VALUES = ("field_changed",)

#: What migrations 0009, 0010 and 0011 created. Downgrade rebuilds ``notification_kind``
#: with just this.
PREVIOUS_NOTIFICATION_KIND_VALUES = (
    "event_request_submitted",
    "coordinator_assigned",
    "equipment_requested",
)

#: Added here (SCRUM-33 AC2).
ADDED_NOTIFICATION_KIND_VALUES = ("significant_change",)


def upgrade() -> None:
    with op.batch_alter_table("event_requests") as batch_op:
        batch_op.add_column(sa.Column("programme_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("internal_planning_notes", sa.Text(), nullable=True))

    # Postgres won't let a transaction use an enum value it added itself, so both
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_HISTORY_KIND_VALUES:
            op.execute(
                sa.text(
                    "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS :value"
                ).bindparams(value=value)
            )
        for value in ADDED_NOTIFICATION_KIND_VALUES:
            op.execute(
                sa.text("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS :value").bindparams(
                    value=value
                )
            )


def downgrade() -> None:
    # Postgres can't remove an enum value, so each type is rebuilt with its previous
    # list and the column re-cast; rows of the removed kind go first. Notifications
    # first, then history entries, mirroring the order they were added in upgrade().
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

    for value in ADDED_HISTORY_KIND_VALUES:
        op.execute(
            sa.text("DELETE FROM event_history_entries WHERE kind = :value").bindparams(value=value)
        )
    op.execute(
        sa.text("ALTER TYPE event_history_entry_kind RENAME TO event_history_entry_kind_old")
    )
    sa.Enum(*PREVIOUS_HISTORY_KIND_VALUES, name="event_history_entry_kind").create(op.get_bind())
    op.execute(
        sa.text(
            "ALTER TABLE event_history_entries ALTER COLUMN kind "
            "TYPE event_history_entry_kind USING kind::text::event_history_entry_kind"
        )
    )
    op.execute(sa.text("DROP TYPE event_history_entry_kind_old"))

    with op.batch_alter_table("event_requests") as batch_op:
        batch_op.drop_column("internal_planning_notes")
        batch_op.drop_column("programme_notes")
