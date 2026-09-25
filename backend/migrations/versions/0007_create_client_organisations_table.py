"""Create client_organisations and link users and event requests to them.

Revision ID: 0007_create_client_organisations
Revises: 0006_add_event_request_statuses
Create Date: 2026-09-25

Schema for SCRUM-66 (ADR-0013): the ``client_organisations`` table with a unique
name, ``users.organisation_id`` for the Event Organiser's organisation, and
``event_requests.organisation_id`` for the organisation a request was submitted
under. Both new columns are nullable: attendees and internal staff have no
organisation, and rows that exist before this migration can't be linked to one
automatically.

The free-text ``users.organisation`` column from SCRUM-65 is dropped, and its values
with it. Downgrading adds the column back empty; the old text is not restored.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_create_client_organisations"
down_revision = "0006_add_event_request_statuses"
branch_labels = None
depends_on = None

#: The foreign keys are named so batch mode can create and drop them on SQLite too.
#: The models leave them unnamed, as ``organiser_id`` does; ``flask db check``
#: compares unnamed foreign keys by their columns, not their names.
USERS_ORGANISATION_FK = "fk_users_organisation_id"
EVENT_REQUESTS_ORGANISATION_FK = "fk_event_requests_organisation_id"


def upgrade() -> None:
    op.create_table(
        "client_organisations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("contact_name", sa.String(length=120), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=False),
        sa.Column("contact_phone", sa.String(length=30), nullable=True),
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
        sa.UniqueConstraint("name", name="uq_client_organisations_name"),
    )

    # batch mode so SQLite can drop columns too; on PostgreSQL it's plain ALTER TABLE.
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("organisation_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            USERS_ORGANISATION_FK, "client_organisations", ["organisation_id"], ["id"]
        )
        batch_op.create_index(
            batch_op.f("ix_users_organisation_id"), ["organisation_id"], unique=False
        )
        batch_op.drop_column("organisation")

    with op.batch_alter_table("event_requests") as batch_op:
        batch_op.add_column(sa.Column("organisation_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            EVENT_REQUESTS_ORGANISATION_FK, "client_organisations", ["organisation_id"], ["id"]
        )
        batch_op.create_index(
            batch_op.f("ix_event_requests_organisation_id"), ["organisation_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("event_requests") as batch_op:
        batch_op.drop_index(batch_op.f("ix_event_requests_organisation_id"))
        batch_op.drop_constraint(EVENT_REQUESTS_ORGANISATION_FK, type_="foreignkey")
        batch_op.drop_column("organisation_id")

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("organisation", sa.String(length=120), nullable=True))
        batch_op.drop_index(batch_op.f("ix_users_organisation_id"))
        batch_op.drop_constraint(USERS_ORGANISATION_FK, type_="foreignkey")
        batch_op.drop_column("organisation_id")

    op.drop_table("client_organisations")
