"""Add the alternative Venue Staff may suggest when they reject a booking request.

Revision ID: 0054_add_suggested_alternative
Revises: 0053_create_change_requests
Create Date: 2026-10-31

SCRUM-70 AC1 "propose one alternative venue, one alternative period, or both"
(ADR-0123):

* ``venue_booking_requests.suggested_venue_id`` names the venue suggested instead.
* ``suggested_starts_at`` and ``suggested_ends_at`` are the period suggested instead.
  The period is whole or absent, and ends after it starts.

All three are nullable: a request has no suggestion until Venue Staff reject it with
one, and every row that exists has none. Downgrading drops the columns, so it is lossy
for any suggestion given since: a suggestion has no other home but the history entry.

Revises 0053 (SCRUM-56), main's head when this was rebased. It adds no enum value, so
it rebuilds no value list. Open pull request #160 (SCRUM-111) adds 0051, with #161 and
#167 (SCRUM-61's 0052) stacked on it; whichever merges later renumbers and re-points
its ``down_revision``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0054_add_suggested_alternative"
down_revision = "0053_create_change_requests"
branch_labels = None
depends_on = None

TABLE = "venue_booking_requests"
SUGGESTED_VENUE_FOREIGN_KEY = "fk_venue_booking_requests_suggested_venue_id"
PERIOD_WHOLE_CHECK = "ck_venue_booking_requests_suggestion_period_whole"
ENDS_AFTER_START_CHECK = "ck_venue_booking_requests_suggestion_ends_after_start"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("suggested_venue_id", sa.Integer(), nullable=True))
    op.add_column(
        TABLE, sa.Column("suggested_starts_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(TABLE, sa.Column("suggested_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        SUGGESTED_VENUE_FOREIGN_KEY, TABLE, "venues", ["suggested_venue_id"], ["id"]
    )
    op.create_check_constraint(
        PERIOD_WHOLE_CHECK,
        TABLE,
        "(suggested_starts_at IS NULL) = (suggested_ends_at IS NULL)",
    )
    op.create_check_constraint(
        ENDS_AFTER_START_CHECK, TABLE, "suggested_ends_at > suggested_starts_at"
    )


def downgrade() -> None:
    op.drop_constraint(ENDS_AFTER_START_CHECK, TABLE, type_="check")
    op.drop_constraint(PERIOD_WHOLE_CHECK, TABLE, type_="check")
    op.drop_constraint(SUGGESTED_VENUE_FOREIGN_KEY, TABLE, type_="foreignkey")
    op.drop_column(TABLE, "suggested_ends_at")
    op.drop_column(TABLE, "suggested_starts_at")
    op.drop_column(TABLE, "suggested_venue_id")
