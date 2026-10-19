"""Add the optional withdrawal cut-off to event requests.

Revision ID: 0042_add_withdrawal_cut_off
Revises: 0041_add_booking_conflicting
Create Date: 2026-10-19

SCRUM-69 AC6 and SCRUM-53 AC3 (ADR-0086):

* ``event_requests.withdrawal_cut_off``, the instant after which Attendees can no
  longer withdraw. Nullable: it stays empty until the assigned coordinator records one,
  and every row that exists keeps closing withdrawals when its event starts.

The column is dropped on downgrade, so it is lossy for any cut-off recorded since: the
cut-off has no other home.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0042_add_withdrawal_cut_off"
down_revision = "0041_add_booking_conflicting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "event_requests",
        sa.Column("withdrawal_cut_off", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("event_requests", "withdrawal_cut_off")
