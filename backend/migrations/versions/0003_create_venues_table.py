"""Create venues and venue_opening_periods tables (venue module).

Revision ID: 0003_create_venues
Revises: 0002_create_event_requests
Create Date: 2026-09-15

Schema for SCRUM-25 (venue catalogue). Weekly opening hours live in a child
table of Google-Places-style periods (ADR-0008).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_create_venues"
down_revision = "0002_create_event_requests"
branch_labels = None
depends_on = None


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
        "venue_opening_periods",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column("open_day", sa.SmallInteger(), nullable=False),
        sa.Column("open_time", sa.Time(), nullable=False),
        sa.Column("close_day", sa.SmallInteger(), nullable=False),
        sa.Column("close_time", sa.Time(), nullable=False),
        sa.CheckConstraint(
            "open_day BETWEEN 0 AND 6", name="ck_venue_opening_periods_open_day_range"
        ),
        sa.CheckConstraint(
            "close_day BETWEEN 0 AND 6", name="ck_venue_opening_periods_close_day_range"
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_venue_opening_periods_venue_id"),
        "venue_opening_periods",
        ["venue_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_venue_opening_periods_venue_id"), table_name="venue_opening_periods")
    op.drop_table("venue_opening_periods")
    op.drop_table("venues")
