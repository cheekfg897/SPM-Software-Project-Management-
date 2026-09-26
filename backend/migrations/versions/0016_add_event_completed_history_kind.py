"""Add the event_completed kind to event history.

Revision ID: 0016_add_event_completed_kind
Revises: 0015_add_event_notes_changes
Create Date: 2026-09-26

SCRUM-68 "Mark an event as completed after it has taken place" (ADR-0027):
``event_history_entry_kind`` gains ``event_completed``, the entry recording which
coordinator marked the event completed, and when (AC5). No table changes: the
``completed`` status itself dates from 0006. ``notification_kind`` is unchanged,
since completing an event notifies no one.

The value is added outside the migration's transaction, with ``IF NOT EXISTS``, as
0012 and 0015 do. Downgrading deletes the history entries of the new kind, since
Postgres can't remove an enum value and the type is rebuilt without it: a lossy
rollback, like theirs. Events already in status ``completed`` keep it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0016_add_event_completed_kind"
down_revision = "0015_add_event_notes_changes"
branch_labels = None
depends_on = None

#: What migrations 0010, 0012 and 0015 created. Downgrade rebuilds
#: ``event_history_entry_kind`` with just this.
PREVIOUS_HISTORY_KIND_VALUES = ("coordinator_assigned", "coordinator_reassigned", "field_changed")

#: Added here (SCRUM-68 AC5).
ADDED_HISTORY_KIND_VALUES = ("event_completed",)


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself, so the
    # addition runs outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_HISTORY_KIND_VALUES:
            op.execute(
                sa.text(
                    "ALTER TYPE event_history_entry_kind ADD VALUE IF NOT EXISTS :value"
                ).bindparams(value=value)
            )


def downgrade() -> None:
    # Postgres can't remove an enum value, so the type is rebuilt with its previous
    # list and the column re-cast; rows of the removed kind go first.
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
