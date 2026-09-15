"""Create venue module tables (venues, bookings, venue_blocks).

Revision ID: 0002_create_venue_tables
Revises: 0001_create_users
Create Date: 2026-09-15

Schema for SCRUM-25 (venue catalogue), SCRUM-26 (availability calendar),
SCRUM-35 (search) and SCRUM-67 (setup/turnaround buffers). ``bookings`` is a
minimal stand-in until an Events module owns real booking creation — see
``app/modules/venue/models.py``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_create_venue_tables"
down_revision = "0001_create_users"
branch_labels = None
depends_on = None


BOOKING_STATUS_VALUES = ("tentative", "confirmed", "cancelled")


def upgrade() -> None:
    op.create_table(
        "venues",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("facilities", sa.String(length=500), nullable=False),
        sa.Column("accessibility_features", sa.String(length=500), nullable=False),
        sa.Column("supported_layouts", sa.String(length=200), nullable=False),
        sa.Column("operating_hours_start", sa.String(length=5), nullable=False),
        sa.Column("operating_hours_end", sa.String(length=5), nullable=False),
        sa.Column("setup_minutes", sa.Integer(), nullable=True),
        sa.Column("turnaround_minutes", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )

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
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_venue_blocks_venue_id"), "venue_blocks", ["venue_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_venue_blocks_venue_id"), table_name="venue_blocks")
    op.drop_table("venue_blocks")

    op.drop_index(op.f("ix_bookings_venue_id"), table_name="bookings")
    op.drop_table("bookings")
    sa.Enum(name="booking_status").drop(op.get_bind(), checkfirst=True)

    op.drop_table("venues")
