"""Add the approved status, the review and decision kinds, and a notification detail.

Revision ID: 0017_add_approval_decisions
Revises: 0016_add_event_completed_kind
Create Date: 2026-09-26

SCRUM-31 "Review and decide a submitted request" (ADR-0028):

* ``notifications`` gains ``detail``, a nullable ``Text`` column that carries the
  reason for a decision to the organiser (AC10, SCRUM-39 AC3).
* ``event_request_status`` gains ``approved``: the coordinator's approval, before the
  event is confirmed (AC4).
* ``event_history_entry_kind`` gains ``review_started`` (AC3) and
  ``decision_recorded`` (AC8).
* ``notification_kind`` gains ``event_request_approved`` and
  ``event_request_rejected`` (AC10).

Every enum value is added outside the migration's transaction, with
``IF NOT EXISTS``, as 0010, 0012 and 0015 do. Downgrading deletes the notifications and
history entries of each new kind, moves an ``approved`` request back to
``under_review``, rebuilds the three enum types without the new values (lossy, like
0006 and 0015), then drops ``detail``. 0014's check constraint is dropped and put back
around the status rebuild, since it would block re-typing the column.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0017_add_approval_decisions"
down_revision = "0016_add_event_completed_kind"
branch_labels = None
depends_on = None

#: What migrations 0002 and 0006 created, in the order Postgres holds them (each
#: ``ADD VALUE`` appends). Downgrade rebuilds ``event_request_status`` with just this.
PREVIOUS_STATUS_VALUES = (
    "submitted",
    "draft",
    "under_review",
    "confirmed",
    "completed",
    "cancelled",
    "rejected",
)

#: Added here (SCRUM-31 AC4).
ADDED_STATUS_VALUES = ("approved",)

#: What migrations 0010, 0012, 0015 and 0016 created. Downgrade rebuilds
#: ``event_history_entry_kind`` with just this.
PREVIOUS_HISTORY_KIND_VALUES = (
    "coordinator_assigned",
    "coordinator_reassigned",
    "field_changed",
    "event_completed",
)

#: Added here (SCRUM-31 AC3, AC8).
ADDED_HISTORY_KIND_VALUES = ("review_started", "decision_recorded")

#: What migrations 0009, 0010, 0011 and 0015 created. Downgrade rebuilds
#: ``notification_kind`` with just this.
PREVIOUS_NOTIFICATION_KIND_VALUES = (
    "event_request_submitted",
    "coordinator_assigned",
    "equipment_requested",
    "significant_change",
)

#: Added here (SCRUM-31 AC10).
ADDED_NOTIFICATION_KIND_VALUES = ("event_request_approved", "event_request_rejected")

#: Migration 0014's check (SCRUM-20, ADR-0024), copied because migrations don't import
#: each other. Downgrade drops it and puts it back around the status re-type.
DETAILS_UNLESS_DRAFT_CHECK_NAME = "ck_event_requests_details_unless_draft"
DETAILS_UNLESS_DRAFT_CHECK_CONDITION = (
    "status = 'draft' OR (proposed_date IS NOT NULL AND end_date IS NOT NULL AND "
    "start_time IS NOT NULL AND end_time IS NOT NULL AND expected_attendance IS NOT NULL)"
)


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(sa.Column("detail", sa.Text(), nullable=True))

    # Postgres won't let a transaction use an enum value it added itself, so every
    # addition runs outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_STATUS_VALUES:
            op.execute(
                sa.text(
                    "ALTER TYPE event_request_status ADD VALUE IF NOT EXISTS :value"
                ).bindparams(value=value)
            )
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
    # list and the column re-cast; rows holding a removed value are deleted or moved
    # first. Notifications, then history entries, then statuses, then the column: the
    # reverse of upgrade().
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

    # An approved request goes back to under review, the status it was approved from
    # or passed through: a lossy rollback, as 0006's is.
    op.execute(
        sa.text("UPDATE event_requests SET status = 'under_review' WHERE status = 'approved'")
    )
    # 0014's check compares status to 'draft', which Postgres can't do across the old
    # and new types, so it blocks the re-type: it comes off first and goes back after.
    op.drop_constraint(DETAILS_UNLESS_DRAFT_CHECK_NAME, "event_requests", type_="check")
    op.execute(sa.text("ALTER TYPE event_request_status RENAME TO event_request_status_old"))
    sa.Enum(*PREVIOUS_STATUS_VALUES, name="event_request_status").create(op.get_bind())
    op.execute(
        sa.text(
            "ALTER TABLE event_requests ALTER COLUMN status "
            "TYPE event_request_status USING status::text::event_request_status"
        )
    )
    op.create_check_constraint(
        DETAILS_UNLESS_DRAFT_CHECK_NAME, "event_requests", DETAILS_UNLESS_DRAFT_CHECK_CONDITION
    )
    op.execute(sa.text("DROP TYPE event_request_status_old"))

    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_column("detail")
