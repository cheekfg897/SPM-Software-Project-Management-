"""Fixtures for the auth module tests."""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.auth.permissions import INTERNAL_ROLES, Role

#: Every internal staff role, in a fixed order so test ids are stable.
STAFF_ROLES = sorted(INTERNAL_ROLES, key=lambda role: role.value)


@pytest.fixture(params=STAFF_ROLES, ids=lambda role: role.value)
def staff_role(request: pytest.FixtureRequest) -> Role:
    """Each internal staff role in turn."""
    return request.param


@pytest.fixture()
def valid_password(valid_registration_payload: dict[str, Any]) -> str:
    """A password that meets the policy (ADR-0005): the registration tests' one.

    Reused rather than typed out again, so the tests keep one copy of it.
    """
    return valid_registration_payload["password"]
