"""Create bookings and venue_blocks tables (venue module).

Revision ID: 0004_create_bookings_and_blocks
Revises: 0003_create_venues
Create Date: 2026-09-15

Schema for SCRUM-26 (availability calendar). ``bookings`` is a minimal
stand-in: SCRUM-19 (events module) only captures a submitted event *request*
so far, with no venue-matching or confirmation workflow yet. Once that lands,
whichever module owns "an event request becomes a confirmed booking" should
own booking creation — see ``app/modules/venue/models.py``. Both tables store
times in UTC and must end after they start (ADR-0009).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_create_bookings_and_blocks"
down_revision = "0003_create_venues"
branch_labels = None
depends_on = None


BOOKING_STATUS_VALUES = ("tentative", "confirmed", "cancelled")


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*BOOKING_STATUS_VALUES, name="booking_status"),
            nullable=False,
        ),
        sa.CheckConstraint("end_time > start_time", name="ck_bookings_ends_after_start"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bookings_venue_id"), "bookings", ["venue_id"], unique=False)

    op.create_table(
        "venue_blocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.CheckConstraint("end_time > start_time", name="ck_venue_blocks_ends_after_start"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_venue_blocks_venue_id"), "venue_blocks", ["venue_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_venue_blocks_venue_id"), table_name="venue_blocks")
    op.drop_table("venue_blocks")

    op.drop_index(op.f("ix_bookings_venue_id"), table_name="bookings")
    op.drop_table("bookings")
    # The PostgreSQL enum type is not dropped by drop_table; remove it
    # explicitly so a downgrade/upgrade cycle can recreate it.
    sa.Enum(name="booking_status").drop(op.get_bind(), checkfirst=True)
