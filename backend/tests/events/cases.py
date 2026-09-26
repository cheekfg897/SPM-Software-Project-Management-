"""Test data the events tests share where no fixture reaches, as in ``parametrize``."""

from __future__ import annotations

from types import SimpleNamespace


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
