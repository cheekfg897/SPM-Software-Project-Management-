"""Create the revoked_tokens table (auth module).

Revision ID: 0048_create_revoked_tokens
Revises: 0047_add_replacement_approved
Create Date: 2026-10-26

SCRUM-89 "No logout; access tokens can't be revoked" (SCRUM-6 AC4, ADR-0110): one
``revoked_tokens`` row per access token logged out before it expired, holding the
token's ``jti``, whose token it was and when it expires. Every protected request checks
it. The unique ``jti`` keeps each token once, whatever the service checks; the index on
``expires_at`` serves each logout's deletion of the rows that have run out.

Revises 0047 (PR #145, SCRUM-92), the newest migration on main when this one was added.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0048_create_revoked_tokens"
down_revision = "0047_add_replacement_approved"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("jti", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti", name="uq_revoked_tokens_jti"),
    )
    op.create_index(
        op.f("ix_revoked_tokens_expires_at"), "revoked_tokens", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_revoked_tokens_expires_at"), table_name="revoked_tokens")
    op.drop_table("revoked_tokens")
