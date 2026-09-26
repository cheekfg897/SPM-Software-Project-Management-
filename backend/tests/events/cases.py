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
