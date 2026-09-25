"""Create the equipment_types table (equipment module).

Revision ID: 0008_create_equipment_types
Revises: 0007_create_client_organisations
Create Date: 2026-09-25

Schema for SCRUM-27 (equipment catalogue). Each type has a unique name and is kept
at exactly one place: a venue or a named store, enforced by a check constraint
(ADR-0014).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0008_create_equipment_types"
down_revision = "0007_create_client_organisations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equipment_types",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("total_quantity", sa.Integer(), nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=True),
        sa.Column("store_name", sa.String(length=200), nullable=True),
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
        sa.CheckConstraint(
            "total_quantity >= 0", name="ck_equipment_types_total_quantity_not_negative"
        ),
        sa.CheckConstraint(
            "(venue_id IS NULL) <> (store_name IS NULL)", name="ck_equipment_types_one_location"
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_equipment_types_name"),
    )
    op.create_index(
        op.f("ix_equipment_types_venue_id"), "equipment_types", ["venue_id"], unique=False
    )


def downgrade() -> None:
    # No Postgres enum type was created, so dropping the table undoes everything.
    op.drop_index(op.f("ix_equipment_types_venue_id"), table_name="equipment_types")
    op.drop_table("equipment_types")
