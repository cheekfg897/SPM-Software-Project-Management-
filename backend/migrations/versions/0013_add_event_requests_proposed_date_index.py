"""Index event requests by proposed date (events module).

Revision ID: 0013_add_proposed_date_index
Revises: 0012_add_reassignment_kind
Create Date: 2026-09-26

SCRUM-38 "See the equipment requests awaiting my action" (ADR-0022): Technical
Support's list keeps only events from today on and puts the soonest first, so it
filters and sorts on ``event_requests.proposed_date``. No data changes.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0013_add_proposed_date_index"
down_revision = "0012_add_reassignment_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_event_requests_proposed_date"),
        "event_requests",
        ["proposed_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_event_requests_proposed_date"), table_name="event_requests")
