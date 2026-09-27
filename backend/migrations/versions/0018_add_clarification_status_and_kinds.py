"""Add the awaiting_clarification status and the clarification kinds.

Revision ID: 0018_add_clarification
Revises: 0017_add_approval_decisions
Create Date: 2026-09-27

SCRUM-32 "Ask the Organiser for clarification" (ADR-0029):

* ``event_request_status`` gains ``awaiting_clarification``: the coordinator has
  asked the organiser a question, and the request is back with the organiser (AC1).
* ``event_history_entry_kind`` gains ``clarification_requested`` and
  ``clarification_answered``, which keep the question and the answer (AC4).
* ``notification_kind`` gains ``clarification_requested`` and
  ``clarification_answered`` (AC1, AC2).

No columns change. Every enum value is added outside the migration's transaction,
with ``IF NOT EXISTS``, as 0010, 0012, 0015 and 0017 do. Downgrading deletes the
notifications and history entries of each new kind, moves a request awaiting
clarification back to ``under_review``, and rebuilds the three enum types without
the new values (lossy, like 0006, 0015 and 0017). The status column can only change
type with 0014's details check out of the way, so that check is dropped and put
back around it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0018_add_clarification"
down_revision = "0017_add_approval_decisions"
branch_labels = None
depends_on = None

#: What migrations 0002, 0006 and 0017 created, in the order Postgres holds them (each
#: ``ADD VALUE`` appends). Downgrade rebuilds ``event_request_status`` with just this.
PREVIOUS_STATUS_VALUES = (
    "submitted",
    "draft",
    "under_review",
    "confirmed",
    "completed",
    "cancelled",
    "rejected",
    "approved",
)

#: Added here (SCRUM-32 AC1).
ADDED_STATUS_VALUES = ("awaiting_clarification",)

#: What migrations 0010, 0012, 0015, 0016 and 0017 created. Downgrade rebuilds
#: ``event_history_entry_kind`` with just this.
PREVIOUS_HISTORY_KIND_VALUES = (
    "coordinator_assigned",
    "coordinator_reassigned",
    "field_changed",
    "event_completed",
    "review_started",
    "decision_recorded",
)

#: Added here (SCRUM-32 AC4).
ADDED_HISTORY_KIND_VALUES = ("clarification_requested", "clarification_answered")

#: What migrations 0009, 0010, 0011, 0015 and 0017 created. Downgrade rebuilds
#: ``notification_kind`` with just this.
PREVIOUS_NOTIFICATION_KIND_VALUES = (
    "event_request_submitted",
    "coordinator_assigned",
    "equipment_requested",
    "significant_change",
    "event_request_approved",
    "event_request_rejected",
)

#: Added here (SCRUM-32 AC1, AC2).
ADDED_NOTIFICATION_KIND_VALUES = ("clarification_requested", "clarification_answered")

#: Migration 0014's check that a request past the draft stage has its details. It
#: compares ``status``, so downgrade drops it while the column changes type, then
#: puts it back as it was. Copied, not imported: migrations don't import each other.
DETAILS_CHECK_NAME = "ck_event_requests_details_unless_draft"
DETAILS_CHECK_CONDITION = (
    "status = 'draft' OR (proposed_date IS NOT NULL AND end_date IS NOT NULL AND "
    "start_time IS NOT NULL AND end_time IS NOT NULL AND expected_attendance IS NOT NULL)"
)


def upgrade() -> None:
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
    # first. Notifications, then history entries, then statuses: the reverse of
    # upgrade().
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

    # A request awaiting clarification goes back to under review, the status the
    # question was asked from: a lossy rollback, as 0017's is.
    op.execute(
        sa.text(
            "UPDATE event_requests SET status = 'under_review' "
            "WHERE status = 'awaiting_clarification'"
        )
    )
    op.execute(sa.text("ALTER TYPE event_request_status RENAME TO event_request_status_old"))
    sa.Enum(*PREVIOUS_STATUS_VALUES, name="event_request_status").create(op.get_bind())
    # Postgres can't re-type a column that a check constraint compares.
    op.drop_constraint(DETAILS_CHECK_NAME, "event_requests", type_="check")
    op.execute(
        sa.text(
            "ALTER TABLE event_requests ALTER COLUMN status "
            "TYPE event_request_status USING status::text::event_request_status"
        )
    )
    op.create_check_constraint(DETAILS_CHECK_NAME, "event_requests", DETAILS_CHECK_CONDITION)
    op.execute(sa.text("DROP TYPE event_request_status_old"))
