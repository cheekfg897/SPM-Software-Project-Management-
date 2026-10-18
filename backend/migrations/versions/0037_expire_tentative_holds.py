"""Expire tentative holds: the expired request status, the warning and the notices.

Revision ID: 0037_expire_tentative_holds
Revises: 0036_add_tentative_holds
Create Date: 2026-10-18

SCRUM-94 "Expire tentative holds automatically" (ADR-0052):

* ``bookings`` gains ``hold_warning_sent_at``, when the coordinator was warned that the
  hold is about to expire, so the warning is sent once.
* ``booking_request_status`` gains ``expired``.
* ``event_history_entry_kind`` gains ``venue_hold_expired``, the entry that keeps an
  expired hold in the event's history.
* ``notification_kind`` gains ``venue_hold_expiring`` and ``venue_hold_expired``, the
  coordinator's warning and expiry notice.

The values are added outside the migration's transaction, with ``IF NOT EXISTS``, as
0025, 0028 and 0036 do. Postgres can't remove an enum value, so downgrading rebuilds the
three types without the new values. An expired request goes back to ``on_hold``, which
loses nothing: its hold's expiry has passed, so 0036's code reads it as expired anyway.
The history entries and notices of the new kinds are deleted, as 0036 deletes its own.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0037_expire_tentative_holds"
down_revision = "0036_add_tentative_holds"
branch_labels = None
depends_on = None

#: What migrations 0020, 0023, 0025, 0028 and 0036 left. Downgrade rebuilds
#: ``booking_request_status`` with just this.
PREVIOUS_REQUEST_STATUS_VALUES = (
    "pending",
    "withdrawn",
    "approved",
    "rejected",
    "conflicting",
    "on_hold",
)

#: Added here (SCRUM-94 AC1, AC2).
ADDED_REQUEST_STATUS_VALUES = ("expired",)

#: The statuses 0036 left the pending index covering; downgrade puts it back so.
PENDING_CONFLICTING_OR_ON_HOLD = "status IN ('pending', 'conflicting', 'on_hold')"

#: What migrations 0010-0036 left (0033 and 0034 added the preparation kinds). Downgrade
#: rebuilds ``event_history_entry_kind`` with
#: just this.
PREVIOUS_HISTORY_KIND_VALUES = (
    "coordinator_assigned",
    "coordinator_reassigned",
    "field_changed",
    "event_completed",
    "review_started",
    "decision_recorded",
    "clarification_requested",
    "clarification_answered",
    "venue_booking_requested",
    "equipment_reserved",
    "venue_arrangement_changed",
    "venue_arrangement_withdrawn",
    "equipment_outcome_recorded",
    "venue_booking_approved",
    "venue_booking_rejected",
    "safety_review_requested",
    "safety_outcome_recorded",
    "event_confirmed",
    "venue_preparation_updated",
    "equipment_preparation_updated",
)

#: Added here (SCRUM-94 AC6): the entry that keeps an expired hold in the history.
ADDED_HISTORY_KIND_VALUES = ("venue_hold_expired",)

#: What migrations 0009-0036 left. Downgrade rebuilds ``notification_kind`` with just
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
    "venue_booking_requested",
    "equipment_reserved",
    "request_queued_for_lead",
    "equipment_outcome_recorded",
    "venue_booking_approved",
    "venue_booking_rejected",
    "safety_review_requested",
    "safety_check_approved",
    "safety_check_rejected",
    "safety_changes_requested",
    "event_confirmed",
    "venue_hold_placed",
    "venue_hold_expiry_changed",
)

#: Added here (SCRUM-94 AC3): the warning 24 hours before, and the expiry notice.
ADDED_NOTIFICATION_KIND_VALUES = ("venue_hold_expiring", "venue_hold_expired")


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
    op.add_column("bookings", sa.Column("hold_warning_sent_at", sa.DateTime(timezone=True)))
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        _add_enum_values("booking_request_status", ADDED_REQUEST_STATUS_VALUES)
        _add_enum_values("event_history_entry_kind", ADDED_HISTORY_KIND_VALUES)
        _add_enum_values("notification_kind", ADDED_NOTIFICATION_KIND_VALUES)


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE venue_booking_requests SET status = 'on_hold' WHERE status = 'expired'")
    )
    for value in ADDED_HISTORY_KIND_VALUES:
        op.execute(
            sa.text("DELETE FROM event_history_entries WHERE kind = :value").bindparams(value=value)
        )
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    op.drop_column("bookings", "hold_warning_sent_at")
    # The pending index's predicate can't be re-created against the renamed enum type,
    # so it is dropped around the rebuild, as 0036 does, and comes back as 0036 left
    # it: Pending, Conflicting and On Hold (SCRUM-42 AC7). Expired requests are back
    # On Hold by now, so they count again, as they did before this migration.
    op.drop_index("uq_venue_booking_requests_pending", table_name="venue_booking_requests")
    _rebuild_enum_without_added_values(
        "booking_request_status",
        "venue_booking_requests",
        "status",
        PREVIOUS_REQUEST_STATUS_VALUES,
    )
    op.create_index(
        "uq_venue_booking_requests_pending",
        "venue_booking_requests",
        ["event_id", "venue_id", "starts_at", "ends_at"],
        unique=True,
        postgresql_where=sa.text(PENDING_CONFLICTING_OR_ON_HOLD),
    )
    _rebuild_enum_without_added_values(
        "event_history_entry_kind",
        "event_history_entries",
        "kind",
        PREVIOUS_HISTORY_KIND_VALUES,
    )
    _rebuild_enum_without_added_values(
        "notification_kind",
        "notifications",
        "kind",
        PREVIOUS_NOTIFICATION_KIND_VALUES,
    )
