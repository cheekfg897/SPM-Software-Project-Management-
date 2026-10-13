"""Record the outcome of an equipment review on each equipment line.

Revision ID: 0024_add_equipment_outcome
Revises: 0023_add_withdrawn_arrangements
Create Date: 2026-10-13

SCRUM-48 "Record the outcome of an equipment review":

* ``event_equipment_lines`` gains ``provided_quantity``, ``outcome_note``,
  ``reviewed_by`` and ``reviewed_at``, and a check that the quantity provided is
  between 0 and the quantity asked for (AC1-AC4).
* ``event_equipment_line_status`` gains ``fulfilled``, ``partially_fulfilled`` and
  ``unavailable`` (AC1-AC3).
* ``event_history_entry_kind`` and ``notification_kind`` gain
  ``equipment_outcome_recorded`` (AC3-AC5).

Values are added outside the migration's transaction, with ``IF NOT EXISTS``, as 0019,
0022 and 0023 do. Downgrading rebuilds the three enum types without the new values
(lossy): a line with an outcome goes back to ``requested`` with its outcome columns
cleared, and the new history entries and notifications are deleted.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0024_add_equipment_outcome"
down_revision = "0023_add_withdrawn_arrangements"
branch_labels = None
depends_on = None

PROVIDED_CHECK = "ck_event_equipment_lines_provided_within_quantity"

#: What migration 0011 created. Downgrade rebuilds ``event_equipment_line_status``
#: with just this.
PREVIOUS_LINE_STATUS_VALUES = ("requested",)

#: Added here (SCRUM-48 AC1-AC3).
ADDED_LINE_STATUS_VALUES = ("fulfilled", "partially_fulfilled", "unavailable")

#: What migrations 0009-0023 left. Downgrade rebuilds ``event_history_entry_kind``
#: with just this.
PREVIOUS_HISTORY_KIND_VALUES = (
    "coordinator_assigned",
    "coordinator_reassigned",
    "field_changed",
    "event_completed",
    "review_started",
    "decision_recorded",
    "clarification_requested",
    "clarification_answered",
    # Added below us in the stack: 0020 (SCRUM-42), 0021 (SCRUM-46) and 0023 (SCRUM-93).
    "venue_booking_requested",
    "equipment_reserved",
    "venue_arrangement_changed",
    "venue_arrangement_withdrawn",
)

#: Added here (SCRUM-48 AC4, AC5).
ADDED_HISTORY_KIND_VALUES = ("equipment_outcome_recorded",)

#: What migrations 0009-0022 left. Downgrade rebuilds ``notification_kind`` with just
#: this.
PREVIOUS_NOTIFICATION_KIND_VALUES = (
    "event_request_submitted",
    "coordinator_assigned",
    "equipment_requested",
    "significant_change",
    "event_request_approved",
    "event_request_rejected",
    "clarification_requested",
    "clarification_answered",
    "request_assigned",
    # Added below us in the stack: 0020 (SCRUM-42), 0021 (SCRUM-46) and 0022 (SCRUM-95).
    "venue_booking_requested",
    "equipment_reserved",
    "request_queued_for_lead",
)

#: Added here (SCRUM-48 AC3).
ADDED_NOTIFICATION_KIND_VALUES = ("equipment_outcome_recorded",)


def _add_enum_values(type_name: str, values: tuple[str, ...]) -> None:
    for value in values:
        op.execute(
            sa.text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS :value").bindparams(
                value=value
            )
        )


def _rebuild_enum_without_added_values(
    type_name: str, table: str, column: str, previous_values: tuple[str, ...]
) -> None:
    # Postgres can't remove an enum value, so the type is rebuilt with its previous
    # list and the column re-cast.
    op.execute(sa.text(f"ALTER TYPE {type_name} RENAME TO {type_name}_old"))
    sa.Enum(*previous_values, name=type_name).create(op.get_bind())
    op.execute(
        sa.text(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE {type_name} USING {column}::text::{type_name}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {type_name}_old"))


def upgrade() -> None:
    op.add_column("event_equipment_lines", sa.Column("provided_quantity", sa.Integer()))
    op.add_column("event_equipment_lines", sa.Column("outcome_note", sa.Text()))
    op.add_column(
        "event_equipment_lines",
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
    )
    op.add_column("event_equipment_lines", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        PROVIDED_CHECK,
        "event_equipment_lines",
        "provided_quantity IS NULL OR provided_quantity BETWEEN 0 AND quantity",
    )
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        _add_enum_values("event_equipment_line_status", ADDED_LINE_STATUS_VALUES)
        _add_enum_values("event_history_entry_kind", ADDED_HISTORY_KIND_VALUES)
        _add_enum_values("notification_kind", ADDED_NOTIFICATION_KIND_VALUES)


def downgrade() -> None:
    # A line with an outcome goes back to waiting for one, and the rows that mention
    # the new kinds are deleted, before each type is rebuilt.
    op.execute(
        sa.text(
            "UPDATE event_equipment_lines SET status = 'requested', provided_quantity = NULL, "
            "outcome_note = NULL, reviewed_by = NULL, reviewed_at = NULL "
            "WHERE status IN ('fulfilled', 'partially_fulfilled', 'unavailable')"
        )
    )
    op.drop_constraint(PROVIDED_CHECK, "event_equipment_lines", type_="check")
    op.drop_column("event_equipment_lines", "reviewed_at")
    op.drop_column("event_equipment_lines", "reviewed_by")
    op.drop_column("event_equipment_lines", "outcome_note")
    op.drop_column("event_equipment_lines", "provided_quantity")
    _rebuild_enum_without_added_values(
        "event_equipment_line_status",
        "event_equipment_lines",
        "status",
        PREVIOUS_LINE_STATUS_VALUES,
    )
    op.execute(
        sa.text("DELETE FROM event_history_entries WHERE kind = 'equipment_outcome_recorded'")
    )
    _rebuild_enum_without_added_values(
        "event_history_entry_kind",
        "event_history_entries",
        "kind",
        PREVIOUS_HISTORY_KIND_VALUES,
    )
    op.execute(sa.text("DELETE FROM notifications WHERE kind = 'equipment_outcome_recorded'"))
    _rebuild_enum_without_added_values(
        "notification_kind",
        "notifications",
        "kind",
        PREVIOUS_NOTIFICATION_KIND_VALUES,
    )
