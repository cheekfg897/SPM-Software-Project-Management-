"""Fixtures for the events module tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, time
from typing import Any

import pytest

from app.modules.events.models import EventRequest, EventRequestStatus


@pytest.fixture()
def today() -> date:
    """A fixed "today" so date rules don't depend on when the tests run."""
    return date(2026, 9, 15)


@pytest.fixture()
def valid_event_request_payload() -> dict[str, Any]:
    """A submission that satisfies every rule, with every field filled in."""
    return {
        "name": "ConnectSphere Partner Summit",
        "purpose": "Annual showcase for partner organisations",
        "description": "Keynotes in the morning, breakout sessions after lunch.",
        "proposed_date": "2026-10-15",
        "start_time": "09:00",
        "end_time": "17:00",
        "expected_attendance": 250,
        "venue_requirements": "Main hall with a stage and 3 breakout rooms",
        "accessibility_needs": "Step-free access and live captioning",
        "equipment_requirements": "2 projectors, PA system, 4 wireless mics",
        "registration_required": True,
    }


@pytest.fixture()
def make_event_request() -> Callable[..., EventRequest]:
    """Factory for in-memory ``EventRequest`` objects.

    Add one to ``db_session`` to persist it. Everything but the three parameters is
    fixed; tests about the other fields go through ``submit_event_request`` with
    ``valid_event_request_payload``.
    """

    def _make(
        *,
        reference: str = "EVR-AAAAAAAA",
        status: EventRequestStatus = EventRequestStatus.SUBMITTED,
        organiser_id: int = 7,
    ) -> EventRequest:
        return EventRequest(
            reference=reference,
            status=status,
            organiser_id=organiser_id,
            name="Partner Summit",
            proposed_date=date(2026, 10, 15),
            end_date=date(2026, 10, 15),
            start_time=time(9, 0),
            end_time=time(17, 0),
            expected_attendance=250,
            registration_required=False,
        )

    return _make
