"""Add setup and turnaround minutes to venues (venue module).

Revision ID: 0005_add_venue_buffer_minutes
Revises: 0004_create_bookings_and_blocks
Create Date: 2026-09-15

Schema for SCRUM-67 (setup/turnaround buffers, ADR-0011). Both columns are NOT NULL,
so no code path has to handle a venue without them. Venues that exist before this
migration get 30 minutes each: the configured default when it was written. The app
sets new venues from its current configuration, so the value here doesn't follow later
config changes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_add_venue_buffer_minutes"
down_revision = "0004_create_bookings_and_blocks"
branch_labels = None
depends_on = None

#: Minutes given to venues that already exist. Hard-coded on purpose: a migration
#: must do the same thing whenever it runs, whatever the app's config says then.
EXISTING_VENUE_MINUTES = 30


def upgrade() -> None:
    # Added as nullable, filled in, then made NOT NULL, so existing rows never break it.
    with op.batch_alter_table("venues") as batch_op:
        batch_op.add_column(sa.Column("setup_minutes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("turnaround_minutes", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            "UPDATE venues SET setup_minutes = :minutes, turnaround_minutes = :minutes"
        ).bindparams(minutes=EXISTING_VENUE_MINUTES)
    )

    with op.batch_alter_table("venues") as batch_op:
        batch_op.alter_column("setup_minutes", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("turnaround_minutes", existing_type=sa.Integer(), nullable=False)
        batch_op.create_check_constraint(
            "ck_venues_setup_minutes_not_negative", "setup_minutes >= 0"
        )
        batch_op.create_check_constraint(
            "ck_venues_turnaround_minutes_not_negative", "turnaround_minutes >= 0"
        )


def downgrade() -> None:
    # batch mode so SQLite can drop columns too; on PostgreSQL it's plain ALTER TABLE.
    with op.batch_alter_table("venues") as batch_op:
        batch_op.drop_constraint("ck_venues_turnaround_minutes_not_negative", type_="check")
        batch_op.drop_constraint("ck_venues_setup_minutes_not_negative", type_="check")
        batch_op.drop_column("turnaround_minutes")
        batch_op.drop_column("setup_minutes")
