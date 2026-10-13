"""Add the withdrawn arrangement status and the arrangement history kinds.

Revision ID: 0023_add_withdrawn_arrangements
Revises: 0022_add_lead_role
Create Date: 2026-10-13

SCRUM-93 "Book several venues for one event" (ADR-0039):

* ``booking_request_status`` gains ``withdrawn``, so a coordinator can retire one of an
  event's arrangements without disturbing the others (AC6).
* ``event_history_entry_kind`` gains ``venue_arrangement_changed`` and
  ``venue_arrangement_withdrawn``, the audit entries for those actions.

``cancelled`` is deliberately **not** added: nothing can produce it until SCRUM-43 gives
an arrangement an ``approved`` status to be cancelled from.

Values are added outside the migration's transaction, with ``IF NOT EXISTS``, as 0019
and 0022 do. Downgrading rebuilds both enum types without the new values and is lossy:
withdrawn arrangements and the new history entries are deleted, not restored. A
withdrawn arrangement is not reverted to ``pending``: that would resurrect a retired
arrangement as live Pending work (and could collide with a re-raised one on the
pending-request unique index), ``withdrawn`` has no earlier representation, and 0022
likewise deletes the rows whose enum value disappears.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0023_add_withdrawn_arrangements"
down_revision = "0022_add_lead_role"
branch_labels = None
depends_on = None

#: What migration 0020 created. Downgrade rebuilds ``booking_request_status`` with this.
PREVIOUS_REQUEST_STATUS_VALUES = ("pending",)

#: Added here (SCRUM-93 AC6).
ADDED_REQUEST_STATUS_VALUES = ("withdrawn",)

#: What migrations 0009-0021 left. Downgrade rebuilds ``event_history_entry_kind``
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
    # Added below us in the stack: 0020 (SCRUM-42) and 0021 (SCRUM-46).
    "venue_booking_requested",
    "equipment_reserved",
)

#: Added here (the audit entries for changing and withdrawing an arrangement).
ADDED_HISTORY_KIND_VALUES = ("venue_arrangement_changed", "venue_arrangement_withdrawn")


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
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        _add_enum_values("booking_request_status", ADDED_REQUEST_STATUS_VALUES)
        _add_enum_values("event_history_entry_kind", ADDED_HISTORY_KIND_VALUES)


def _drop_pending_index() -> None:
    op.drop_index("uq_venue_booking_requests_pending", table_name="venue_booking_requests")


def _create_pending_index() -> None:
    # Same definition as migration 0020 (SCRUM-42 AC6).
    op.create_index(
        "uq_venue_booking_requests_pending",
        "venue_booking_requests",
        ["event_id", "venue_id", "starts_at", "ends_at"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM venue_booking_requests WHERE status = 'withdrawn'"))
    # The pending index's predicate (status = 'pending') can't be re-created against
    # the renamed enum type, so it is dropped around the rebuild.
    _drop_pending_index()
    _rebuild_enum_without_added_values(
        "booking_request_status",
        "venue_booking_requests",
        "status",
        PREVIOUS_REQUEST_STATUS_VALUES,
    )
    _create_pending_index()
    for value in ADDED_HISTORY_KIND_VALUES:
        op.execute(
            sa.text("DELETE FROM event_history_entries WHERE kind = :value").bindparams(value=value)
        )
    _rebuild_enum_without_added_values(
        "event_history_entry_kind",
        "event_history_entries",
        "kind",
        PREVIOUS_HISTORY_KIND_VALUES,
    )
