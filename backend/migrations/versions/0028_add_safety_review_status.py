"""Add the safety_review status.

Revision ID: 0028_add_safety_review
Revises: 0027_create_registrations
Create Date: 2026-10-17

SCRUM-22 "Define the event status model" (ADR-0045): ``event_request_status`` gains
``safety_review``, the tenth status, between ``approved`` and ``confirmed``. Nothing
moves an event into it yet; SCRUM-97 and SCRUM-49 do.

No columns change. The value is added outside the migration's transaction, with
``IF NOT EXISTS``, as 0017 and 0018 do. Downgrading moves an event in safety review
back to ``approved`` and rebuilds the type without the new value (lossy, like 0017
and 0018). The status column can only change type with 0014's details check out of
the way, so that check is dropped and put back around it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0028_add_safety_review"
down_revision = "0027_create_registrations"
branch_labels = None
depends_on = None

#: What migrations 0002, 0006, 0017 and 0018 created, in the order Postgres holds them
#: (each ``ADD VALUE`` appends). Downgrade rebuilds ``event_request_status`` with just
#: this.
PREVIOUS_STATUS_VALUES = (
    "submitted",
    "draft",
    "under_review",
    "confirmed",
    "completed",
    "cancelled",
    "rejected",
    "approved",
    "awaiting_clarification",
)

#: Added here (SCRUM-22, ADR-0045).
ADDED_STATUS_VALUES = ("safety_review",)

#: Migration 0014's check that a request past the draft stage has its details. It
#: compares ``status``, so downgrade drops it while the column changes type, then
#: puts it back as it was. Copied, not imported: migrations don't import each other.
DETAILS_CHECK_NAME = "ck_event_requests_details_unless_draft"
DETAILS_CHECK_CONDITION = (
    "status = 'draft' OR (proposed_date IS NOT NULL AND end_date IS NOT NULL AND "
    "start_time IS NOT NULL AND end_time IS NOT NULL AND expected_attendance IS NOT NULL)"
)


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself, so the
    # addition runs outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_STATUS_VALUES:
            op.execute(
                sa.text(
                    "ALTER TYPE event_request_status ADD VALUE IF NOT EXISTS :value"
                ).bindparams(value=value)
            )


def downgrade() -> None:
    # Postgres can't remove an enum value, so the type is rebuilt with its previous
    # list and the column re-cast; an event in safety review goes back to approved, the
    # status it was sent to the check from: a lossy rollback, as 0017's and 0018's are.
    op.execute(
        sa.text("UPDATE event_requests SET status = 'approved' WHERE status = 'safety_review'")
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
