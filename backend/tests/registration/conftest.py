"""Fixtures for the registration module tests (SCRUM-52)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest

from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events.models import EventRequest
from app.modules.registration.models import Registration, RegistrationStatus

#: Every role but Attendee, in a fixed order so test ids are stable.
NON_ATTENDEE_ROLES = sorted(ALL_ROLES - {Role.ATTENDEE}, key=lambda role: role.value)


@pytest.fixture(params=NON_ATTENDEE_ROLES, ids=lambda role: role.value)
def non_attendee_role(request: pytest.FixtureRequest) -> Role:
    """Each role but Attendee in turn, for routes only attendees call."""
    return request.param


@pytest.fixture()
def make_registration(save: Callable[..., None], now: datetime) -> Callable[..., Registration]:
    """Factory for saved registrations; ``registered_at`` defaults to ``now``."""

    def _make(
        event: EventRequest, attendee_id: int, *, registered_at: datetime | None = None
    ) -> Registration:
        registration = Registration(
            event_request_id=event.id,
            attendee_id=attendee_id,
            status=RegistrationStatus.REGISTERED,
            registered_at=registered_at if registered_at is not None else now,
        )
        save(registration)
        return registration

    return _make
