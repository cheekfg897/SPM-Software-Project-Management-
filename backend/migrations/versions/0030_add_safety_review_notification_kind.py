"""Add the safety_review_requested notification kind.

Revision ID: 0030_add_safety_review_kind
Revises: 0029_add_safety_review
Create Date: 2026-10-16

SCRUM-97 "Submit an event for operational safety check" (ADR-0047):

* ``notification_kind`` gains ``safety_review_requested``, raised to every Safety
  Officer when an event enters Safety Review (AC4).

The enum value is added outside the migration's transaction, with ``IF NOT EXISTS``,
as 0019 does. Downgrading deletes the rows of the new kind and rebuilds the enum type
without it (lossy, like 0019's).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0030_add_safety_review_kind"
down_revision = "0029_add_safety_review"
branch_labels = None
depends_on = None

#: What migrations 0009-0025 left, in the order Postgres holds them. Downgrade rebuilds
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
)

#: Added here (SCRUM-97 AC4).
ADDED_NOTIFICATION_KIND_VALUES = ("safety_review_requested",)


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself, so the
    # addition runs outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_NOTIFICATION_KIND_VALUES:
            op.execute(
                sa.text("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS :value").bindparams(
                    value=value
                )
            )


def downgrade() -> None:
    # Postgres can't remove an enum value, so the type is rebuilt with its previous
    # list and the column re-cast; rows of the removed kind go first.
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
