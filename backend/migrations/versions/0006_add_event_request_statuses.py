"""Add the remaining event request statuses (events module).

Revision ID: 0006_add_event_request_statuses
Revises: 0005_add_venue_buffer_minutes
Create Date: 2026-09-25

SCRUM-22 "Define the event status model" (ADR-0012): ``event_request_status`` grows
from ``submitted`` alone to the story's seven statuses. Rows are left as they are;
every existing request stays ``submitted``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_add_event_request_statuses"
down_revision = "0005_add_venue_buffer_minutes"
branch_labels = None
depends_on = None

#: What migration 0002 created. Downgrade rebuilds the type with just this.
PREVIOUS_STATUS_VALUES = ("submitted",)

#: Added here, in lifecycle order (ADR-0012).
ADDED_STATUS_VALUES = ("draft", "under_review", "confirmed", "completed", "cancelled", "rejected")


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself (and before
    # version 12 refuses ADD VALUE inside a transaction at all), so the additions run
    # outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_STATUS_VALUES:
            op.execute(
                sa.text("ALTER TYPE event_request_status ADD VALUE :value").bindparams(value=value)
            )


def downgrade() -> None:
    # Postgres can't remove enum values, so the type is rebuilt with the original list
    # and the column re-cast. A row in a status that no longer exists goes back to
    # ``submitted``: a lossy rollback, but the only status this schema knows.
    op.execute(
        sa.text("UPDATE event_requests SET status = 'submitted' WHERE status != 'submitted'")
    )
    op.execute(sa.text("ALTER TYPE event_request_status RENAME TO event_request_status_old"))
    sa.Enum(*PREVIOUS_STATUS_VALUES, name="event_request_status").create(op.get_bind())
    op.execute(
        sa.text(
            "ALTER TABLE event_requests ALTER COLUMN status "
            "TYPE event_request_status USING status::text::event_request_status"
        )
    )
    op.execute(sa.text("DROP TYPE event_request_status_old"))
