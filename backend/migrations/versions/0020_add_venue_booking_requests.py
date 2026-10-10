"""Add venue booking requests.

Revision ID: 0020_add_venue_booking_requests
Revises: 0019_add_review_kinds
Create Date: 2026-10-10

SCRUM-42 "Request a venue booking for an approved event" (ADR-0035):

* ``venue_booking_requests`` holds one request for a venue and period, with its
  purpose, expected occupancy, required layout and (AC7) justification. The
  ``booking_request_status`` enum has only ``pending`` so far.
* ``event_history_entry_kind`` gains ``venue_booking_requested``, the audit entry
  written in the same commit as the request.
* ``notification_kind`` gains ``venue_booking_requested``, the notice to Venue Staff
  (AC9).

The enum values are added outside the migration's transaction, with ``IF NOT EXISTS``,
as 0016 and 0019 do. Downgrading drops the table and its enum type, deletes the rows of
the new kinds, and rebuilds both kind types without them (lossy, like 0018's).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0020_add_venue_booking_requests"
down_revision = "0019_add_review_kinds"
branch_labels = None
depends_on = None

#: Only ``pending`` is written so far; SCRUM-43 adds approving and rejecting.
REQUEST_STATUS_VALUES = ("pending",)

#: What migrations 0010, 0012, 0015, 0016, 0017 and 0018 created. Downgrade rebuilds
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
)

#: Added here (the audit entry for a raised request).
ADDED_HISTORY_KIND_VALUES = ("venue_booking_requested",)

#: What migrations 0009, 0010, 0011, 0015, 0017, 0018 and 0019 created. Downgrade
#: rebuilds ``notification_kind`` with just this.
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
)

#: Added here (SCRUM-42 AC9).
ADDED_NOTIFICATION_KIND_VALUES = ("venue_booking_requested",)


def _rebuild_enum_without_added_values(
    enum_name: str, table: str, previous_values: tuple[str, ...], added_values: tuple[str, ...]
) -> None:
    """Delete the rows using ``added_values``, then rebuild ``enum_name`` without them.

    Postgres can't remove an enum value, so the type is renamed, recreated with its
    previous list, and the table's ``kind`` column re-cast.
    """
    # ``table`` is one of this module's own constants, never user input.
    delete_rows = sa.text(f"DELETE FROM {table} WHERE kind = :value")  # noqa: S608
    for value in added_values:
        op.execute(delete_rows.bindparams(value=value))
    op.execute(sa.text(f"ALTER TYPE {enum_name} RENAME TO {enum_name}_old"))
    sa.Enum(*previous_values, name=enum_name).create(op.get_bind())
    op.execute(
        sa.text(
            f"ALTER TABLE {table} ALTER COLUMN kind TYPE {enum_name} USING kind::text::{enum_name}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {enum_name}_old"))


def _add_enum_values(enum_name: str, values: tuple[str, ...]) -> None:
    """Add ``values`` to ``enum_name`` (the caller sits inside ``autocommit_block``)."""
    for value in values:
        op.execute(
            sa.text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS :value").bindparams(
                value=value
            )
        )


def upgrade() -> None:
    op.create_table(
        "venue_booking_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("expected_occupancy", sa.Integer(), nullable=False),
        sa.Column("required_layout", sa.String(length=50), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(*REQUEST_STATUS_VALUES, name="booking_request_status"),
            nullable=False,
        ),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ends_at > starts_at", name="ck_venue_booking_requests_ends_after_start"
        ),
        sa.CheckConstraint(
            "expected_occupancy >= 1", name="ck_venue_booking_requests_occupancy_min"
        ),
        sa.ForeignKeyConstraint(["event_id"], ["event_requests.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_venue_booking_requests_event_id"), "venue_booking_requests", ["event_id"]
    )
    op.create_index(
        op.f("ix_venue_booking_requests_venue_id"), "venue_booking_requests", ["venue_id"]
    )
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        _add_enum_values("event_history_entry_kind", ADDED_HISTORY_KIND_VALUES)
        _add_enum_values("notification_kind", ADDED_NOTIFICATION_KIND_VALUES)


def downgrade() -> None:
    # The reverse of upgrade(): kinds first, then the table, then its enum type
    # (drop_table leaves the type behind, and CI replays downgrade then upgrade).
    _rebuild_enum_without_added_values(
        "notification_kind",
        "notifications",
        PREVIOUS_NOTIFICATION_KIND_VALUES,
        ADDED_NOTIFICATION_KIND_VALUES,
    )
    _rebuild_enum_without_added_values(
        "event_history_entry_kind",
        "event_history_entries",
        PREVIOUS_HISTORY_KIND_VALUES,
        ADDED_HISTORY_KIND_VALUES,
    )
    op.drop_table("venue_booking_requests")
    sa.Enum(name="booking_request_status").drop(op.get_bind())
