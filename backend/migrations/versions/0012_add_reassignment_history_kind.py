"""Add the reassignment kind to event history.

Revision ID: 0012_add_reassignment_kind
Revises: 0011_create_equipment_lines
Create Date: 2026-09-26

SCRUM-87 "Reassign an event to a different coordinator" (ADR-0021):
``event_history_entry_kind`` gains ``coordinator_reassigned``, the entry recording
who moved an event from which coordinator to which, and when (AC3, AC7).
``notification_kind`` is unchanged: only the new coordinator is told, with the
existing ``coordinator_assigned``.

The value is added outside the migration's transaction, with ``IF NOT EXISTS``, as
0010 does. Downgrading deletes the history entries of the new kind, since Postgres
can't remove an enum value and the type is rebuilt without it: a lossy rollback,
like 0010's.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0012_add_reassignment_kind"
down_revision = "0011_create_equipment_lines"
branch_labels = None
depends_on = None

#: What migration 0010 created. Downgrade rebuilds ``event_history_entry_kind`` with
#: just this.
PREVIOUS_HISTORY_KIND_VALUES = ("coordinator_assigned",)

#: Added here (SCRUM-87 AC3, AC7).
ADDED_HISTORY_KIND_VALUES = ("coordinator_reassigned",)


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
    # list and the column re-cast; entries of the removed kind go first.
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
