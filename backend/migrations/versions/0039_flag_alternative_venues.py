"""Flag venue arrangements that need an alternative venue.

Revision ID: 0039_flag_alternative_venues
Revises: 0037_expire_tentative_holds
Create Date: 2026-10-18

SCRUM-92 "Flag bookings affected when a venue becomes unavailable" (ADR-0053):

* ``unavailability_category`` is a new type for why a venue can't be used (AC2).
  ``venue_blocks.category`` holds it; a block saved before this migration becomes
  ``other``, with its reason as the note.
* ``alternative_venue_flags`` holds one row for each block or deactivation that left
  an arrangement needing another venue, with the category, note and period (AC1, AC9).
* ``venue_booking_requests.replaces_request_id`` links a replacement request to the
  arrangement it replaces (AC6).
* ``booking_request_status`` gains ``released``, for an arrangement whose replacement
  was approved (AC7).
* ``notification_kind`` gains ``alternative_venue_needed`` (AC5), and
  ``event_history_entry_kind`` gains ``alternative_venue_needed`` and
  ``safety_approval_withdrawn`` (AC3, AC10).

Revises 0037, main's head when it was rebased; whichever open migration merges later
re-points its ``down_revision`` and, if it changed one of the enum types below, adds
its values to this file's ``PREVIOUS_*`` lists. Each value is
added outside the migration's transaction, with ``IF NOT EXISTS``, as 0035 does.
Downgrading deletes the rows of the new kinds, turns a Released arrangement into a
Withdrawn one (both retire it), and rebuilds each type without the new values.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0039_flag_alternative_venues"
down_revision = "0037_expire_tentative_holds"
branch_labels = None
depends_on = None

#: The new type's values (AC2).
CATEGORY_VALUES = ("maintenance", "equipment_failure", "renovation", "safety_concern", "other")
CATEGORY_TYPE = "unavailability_category"

#: What migrations 0020-0037 left. Downgrade rebuilds ``booking_request_status`` with
#: just this.
PREVIOUS_REQUEST_STATUS_VALUES = (
    "pending",
    "withdrawn",
    "approved",
    "rejected",
    "conflicting",
    "on_hold",
    "expired",
)
#: Added here (AC7).
ADDED_REQUEST_STATUS_VALUES = ("released",)

#: What migrations 0010-0037 left, in the order Postgres holds them. Downgrade rebuilds
#: ``event_history_entry_kind`` with just this.
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
    "venue_hold_expired",
)
#: Added here (AC3, AC10).
ADDED_HISTORY_KIND_VALUES = ("alternative_venue_needed", "safety_approval_withdrawn")

#: What migrations 0009-0037 left, in the order Postgres holds them. Downgrade rebuilds
#: ``notification_kind`` with just this.
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
    "venue_hold_expiring",
    "venue_hold_expired",
)
#: Added here (AC5).
ADDED_NOTIFICATION_KIND_VALUES = ("alternative_venue_needed",)

#: The pending index 0036 left, which the request status rebuild has to drop and put
#: back: its predicate can't be re-created against the renamed type.
PENDING_INDEX = "uq_venue_booking_requests_pending"
PENDING_CONFLICTING_OR_ON_HOLD = "status IN ('pending', 'conflicting', 'on_hold')"
REPLACES_FOREIGN_KEY = "fk_venue_booking_requests_replaces_request_id"


def _category_type() -> postgresql.ENUM:
    # create_type=False: the type is created once, explicitly, before either column
    # uses it. Only Postgres's ENUM honours it on SQLAlchemy 2.0 (as in 0021); the
    # generic sa.Enum ignores it there, and create_table makes the type a second time.
    return postgresql.ENUM(*CATEGORY_VALUES, name=CATEGORY_TYPE, create_type=False)


def _add_enum_values(type_name: str, values: tuple[str, ...]) -> None:
    for value in values:
        op.execute(
            sa.text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS :value").bindparams(
                value=value
            )
        )


def _rebuild_enum(
    type_name: str, table: str, column: str, previous_values: tuple[str, ...]
) -> None:
    # Postgres can't remove an enum value, so the type is rebuilt with its previous
    # list and the table's column re-cast.
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
    sa.Enum(*CATEGORY_VALUES, name=CATEGORY_TYPE).create(op.get_bind())
    # Blocks saved before AC2 have only a note, so they become "other"; the default is
    # dropped again so a new block must name its category.
    op.add_column(
        "venue_blocks",
        sa.Column("category", _category_type(), nullable=False, server_default="other"),
    )
    op.alter_column("venue_blocks", "category", server_default=None)

    op.create_table(
        "alternative_venue_flags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("booking_request_id", sa.Integer(), nullable=False),
        sa.Column("venue_block_id", sa.Integer(), nullable=True),
        sa.Column("category", _category_type(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["booking_request_id"], ["venue_booking_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["venue_block_id"], ["venue_blocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_alternative_venue_flags_booking_request_id"),
        "alternative_venue_flags",
        ["booking_request_id"],
    )
    op.create_index(
        op.f("ix_alternative_venue_flags_venue_block_id"),
        "alternative_venue_flags",
        ["venue_block_id"],
    )

    op.add_column(
        "venue_booking_requests", sa.Column("replaces_request_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        REPLACES_FOREIGN_KEY,
        "venue_booking_requests",
        "venue_booking_requests",
        ["replaces_request_id"],
        ["id"],
    )

    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        _add_enum_values("booking_request_status", ADDED_REQUEST_STATUS_VALUES)
        _add_enum_values("event_history_entry_kind", ADDED_HISTORY_KIND_VALUES)
        _add_enum_values("notification_kind", ADDED_NOTIFICATION_KIND_VALUES)


def downgrade() -> None:
    # The rows holding a removed value go first; then each type is rebuilt without it.
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    _rebuild_enum("notification_kind", "notifications", "kind", PREVIOUS_NOTIFICATION_KIND_VALUES)
    for value in ADDED_HISTORY_KIND_VALUES:
        op.execute(
            sa.text("DELETE FROM event_history_entries WHERE kind = :value").bindparams(value=value)
        )
    _rebuild_enum(
        "event_history_entry_kind", "event_history_entries", "kind", PREVIOUS_HISTORY_KIND_VALUES
    )

    # A Released arrangement no longer holds its venue, as a Withdrawn one doesn't, and
    # neither is Pending, Conflicting or On Hold, so the change can't break the pending
    # index.
    op.drop_index(PENDING_INDEX, table_name="venue_booking_requests")
    op.execute(
        sa.text("UPDATE venue_booking_requests SET status='withdrawn' WHERE status = 'released'")
    )
    _rebuild_enum(
        "booking_request_status", "venue_booking_requests", "status", PREVIOUS_REQUEST_STATUS_VALUES
    )
    op.create_index(
        PENDING_INDEX,
        "venue_booking_requests",
        ["event_id", "venue_id", "starts_at", "ends_at"],
        unique=True,
        postgresql_where=sa.text(PENDING_CONFLICTING_OR_ON_HOLD),
    )

    op.drop_constraint(REPLACES_FOREIGN_KEY, "venue_booking_requests", type_="foreignkey")
    op.drop_column("venue_booking_requests", "replaces_request_id")
    op.drop_index(
        op.f("ix_alternative_venue_flags_venue_block_id"), table_name="alternative_venue_flags"
    )
    op.drop_index(
        op.f("ix_alternative_venue_flags_booking_request_id"), table_name="alternative_venue_flags"
    )
    op.drop_table("alternative_venue_flags")
    op.drop_column("venue_blocks", "category")
    sa.Enum(name=CATEGORY_TYPE).drop(op.get_bind(), checkfirst=True)
