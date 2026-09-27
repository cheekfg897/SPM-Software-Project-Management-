"""Test data the events tests share where no fixture reaches, as in ``parametrize``."""

from __future__ import annotations

from types import SimpleNamespace

from app.modules.events.models import EventRequestStatus


class DriverError(Exception):
    """Stands in for a psycopg2 error, naming the constraint it violated on ``diag``.

    A class here rather than a fixture: tests build one as a literal inside
    ``parametrize``, where a fixture cannot reach.
    """

    def __init__(self, constraint_name: str | None, message: str = "integrity error") -> None:
        super().__init__(message)
        self.diag = SimpleNamespace(constraint_name=constraint_name)


#: A fixed reference for tests that save a draft (SCRUM-20), so they need not read it
#: back off the returned object just to look it up again.
DRAFT_REFERENCE = "EVR-DDDDDDDD"

#: The five columns a draft may leave empty and every other request must have
#: (SCRUM-20, ADR-0024).
DETAIL_COLUMNS = ["proposed_date", "end_date", "start_time", "end_time", "expected_attendance"]

#: Every status but draft, so "past the draft stage" can be checked as a whole.
NON_DRAFT_STATUSES = [
    status for status in EventRequestStatus if status is not EventRequestStatus.DRAFT
]

#: One field at a time, each with a value its own rule refuses, whether the field
#: is sent on a save or on an edit: the per-field rule does not care which (SCRUM-20).
FIELD_REJECTED_CASES = [
    ("proposed_date", "soon"),
    ("start_time", "25:00"),
    ("start_time", "09:00+08:00"),
    ("expected_attendance", 0),
    ("expected_attendance", "50"),
    ("expected_attendance", True),
    ("registration_required", "yes"),
]

#: Reasons a coordinator gives for a decision (SCRUM-31 AC4, AC6).
APPROVAL_REASON = "The venue and date fit the brief."
REJECTION_REASON = "The venue is too small for the expected attendance."

#: A coordinator's question to the organiser (SCRUM-32 AC1).
CLARIFICATION_QUESTION = "Will any guests need step-free access to the stage?"
