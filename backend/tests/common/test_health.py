"""Unit tests for the health endpoint, ``GET /health`` (SCRUM-5).

Deployment probes and CI's smoke-test step read this route to tell an outage from a
healthy app, so it has to answer ``503`` when the database doesn't. The smoke test only
ever sees a working database, which leaves the outage answer to these tests. A real
query runs on the in-memory database; the outage replaces it with one that fails.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.extensions import db

pytestmark = pytest.mark.scrum_5

HEALTH_ROUTE = ("health.health", "GET", "/health", {}, None)


def _make_the_query_raise(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(db.session, "execute", MagicMock(side_effect=error))


def test_answers_200_when_the_database_answers(call_route: Callable[..., Any]) -> None:
    response, status = call_route(*HEALTH_ROUTE)

    assert status == 200
    assert response.get_json() == {"status": "ok", "database": "ok"}


def test_answers_503_and_logs_why_when_the_database_does_not_answer(
    call_route: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    outage = OperationalError("SELECT 1", {}, Exception("connection refused"))
    _make_the_query_raise(monkeypatch, outage)

    with caplog.at_level(logging.WARNING):
        response, status = call_route(*HEALTH_ROUTE)

    assert status == 503
    assert response.get_json() == {"status": "unhealthy", "database": "unreachable"}
    assert "Health check could not reach the database" in caplog.text
    assert "connection refused" in caplog.text


def test_a_fault_outside_the_database_is_not_reported_as_an_outage(
    call_route: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_the_query_raise(monkeypatch, RuntimeError("a bug in the app"))

    with pytest.raises(RuntimeError, match="a bug in the app"):
        call_route(*HEALTH_ROUTE)
