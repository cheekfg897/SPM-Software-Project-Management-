"""Let a draft event request leave its details empty (events module).

Revision ID: 0014_allow_incomplete_drafts
Revises: 0013_add_proposed_date_index
Create Date: 2026-09-26

SCRUM-20 "Save and resume a draft event request" AC1 (ADR-0024): an Organiser can
save a request with only its name. The five columns that describe when and how big
the event is (``proposed_date``, ``end_date``, ``start_time``, ``end_time``,
``expected_attendance``) become nullable, and a check constraint requires all five
once a request leaves the draft stage, so the database enforces the same rule the
service does.

Downgrading a draft that never got its details deletes it: restoring ``NOT NULL``
with no value to put there is impossible, so a request with any of the five still
empty is removed first. A lossy rollback, like 0006 and 0010.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0014_allow_incomplete_drafts"
down_revision = "0013_add_proposed_date_index"
branch_labels = None
depends_on = None

#: The five columns a draft may leave empty, with the type each already has.
DRAFT_OPTIONAL_COLUMNS = (
    ("proposed_date", sa.Date()),
    ("end_date", sa.Date()),
    ("start_time", sa.Time()),
    ("end_time", sa.Time()),
    ("expected_attendance", sa.Integer()),
)

CHECK_NAME = "ck_event_requests_details_unless_draft"
CHECK_CONDITION = (
    "status = 'draft' OR (proposed_date IS NOT NULL AND end_date IS NOT NULL AND "
    "start_time IS NOT NULL AND end_time IS NOT NULL AND expected_attendance IS NOT NULL)"
)

#: What a downgrade must remove before ``NOT NULL`` can come back: a draft that was
#: saved with any of the five still empty. A plain string, not an f-string: nothing in
#: it is user input.
DELETE_INCOMPLETE_DRAFTS = (
    "DELETE FROM event_requests WHERE status = 'draft' AND ("
    "proposed_date IS NULL OR end_date IS NULL OR "
    "start_time IS NULL OR end_time IS NULL OR expected_attendance IS NULL"
    ")"
)


def upgrade() -> None:
    for column_name, column_type in DRAFT_OPTIONAL_COLUMNS:
        op.alter_column("event_requests", column_name, existing_type=column_type, nullable=True)
    op.create_check_constraint(CHECK_NAME, "event_requests", CHECK_CONDITION)


def downgrade() -> None:
    op.drop_constraint(CHECK_NAME, "event_requests", type_="check")
    op.execute(sa.text(DELETE_INCOMPLETE_DRAFTS))
    for column_name, column_type in DRAFT_OPTIONAL_COLUMNS:
        op.alter_column("event_requests", column_name, existing_type=column_type, nullable=False)
