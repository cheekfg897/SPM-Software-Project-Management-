"""Create users table (auth module).

Revision ID: 0001_create_users
Revises:
Create Date: 2026-09-15

Initial schema for the auth module: the ``users`` table with a unique,
indexed email, a hashed password, the ``user_role`` enum and timestamps.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_create_users"
down_revision = None
branch_labels = None
depends_on = None


ROLE_VALUES = (
    "event_organiser",
    "attendee",
    "event_coordinator",
    "venue_staff",
    "technical_support_staff",
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.Enum(*ROLE_VALUES, name="user_role"), nullable=False),
        sa.Column("organisation", sa.String(length=120), nullable=True),
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
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    # The PostgreSQL enum type is not dropped by drop_table; remove it
    # explicitly. checkfirst makes this a no-op on databases without CREATE TYPE.
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
