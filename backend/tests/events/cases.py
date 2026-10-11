"""Test data the events tests share where no fixture reaches, as in ``parametrize``."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

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

#: A draft with every field a submission needs, so it can be submitted as it stands
#: (SCRUM-20). Shared by the tests that submit a draft.
COMPLETE_DRAFT_PAYLOAD = {
    "name": "Partner Summit",
    "proposed_date": "2026-10-15",
    "start_time": "09:00",
    "end_time": "17:00",
    "expected_attendance": 250,
}

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
#: The organiser's answer to it (SCRUM-32 AC2).
CLARIFICATION_RESPONSE = "Yes: two speakers use wheelchairs, so we need a ramp."

#: Changes that break the time window once merged with a saved request running
#: 2026-10-15 09:00-17:00, with the error each gets (ADR-0002, ADR-0025). Shared by the
#: coordinator's edit (SCRUM-33) and the organiser's amendment (SCRUM-32).
WINDOW_VIOLATIONS = [
    ({"end_time": "08:00"}, {"end_time": ["Event must end after it starts."]}),
    ({"start_time": "18:00"}, {"end_time": ["Event must end after it starts."]}),
    (
        {"end_date": "2026-10-14"},
        {"end_date": ["End date cannot be before the proposed date."]},
    ),
]
WINDOW_VIOLATION_IDS = [
    "end-time-before-current-start",
    "start-time-after-current-end",
    "end-date-before-current-proposed-date",
]

#: A dropped database connection, as a failed notification write raises it (ADR-0015).
LOST_CONNECTION = OperationalError("INSERT INTO notifications ...", {}, Exception("gone"))

#: Which notification write is lost once an assignment is saved: the session's
#: commits in order (the change's own, the coordinator's notice, then the organiser's),
#: and the kind the warning names (SCRUM-39 AC1, ADR-0015). Losing one notice still
#: sends the other.
LOST_NOTIFICATION_CASES = [
    pytest.param([None, LOST_CONNECTION, None], "coordinator_assigned", id="the-coordinators"),
    pytest.param([None, None, LOST_CONNECTION], "request_assigned", id="the-organisers"),
]

#: The Event Coordinator Lead who assigns a request in the tests (SCRUM-95 AC3). The
#: assign service records the actor's id and never looks the actor up — the route's
#: ``@requires_role`` is what proves they are the Lead — so no user with this id need
#: be saved. Shared by the ``lead_assigns`` fixture and the tests that read the audit
#: entry back.
LEAD_ID = 11
