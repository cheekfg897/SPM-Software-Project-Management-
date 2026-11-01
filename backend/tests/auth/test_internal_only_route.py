"""Unit tests for the staff route, ``GET /api/auth/internal-only`` (SCRUM-21 AC5).

``tests/auth/test_permissions.py`` wraps a dummy view in ``requires_role``. These
check the route's real wiring: every staff role is let in and told its role, and
every other role is refused before the view can answer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import ALL_ROLES, INTERNAL_ROLES, Role

pytestmark = pytest.mark.scrum_21

INTERNAL_ONLY_ROUTE = ("auth.internal_only", "GET", "/api/auth/internal-only", {})
#: Built from the role groups, so a role added later is refused here unless it is staff.
ROLES_REFUSED = sorted(ALL_ROLES - INTERNAL_ROLES, key=lambda role: role.value)


def test_each_staff_role_is_answered_with_its_own_role(
    call_route: Callable[..., Any], token_for: Callable[..., str], staff_role: Role
) -> None:
    response, status = call_route(*INTERNAL_ONLY_ROUTE, token_for(role=staff_role))

    assert status == 200
    assert response.get_json() == {
        "message": "Hello, internal staff.",
        "role": staff_role.value,
    }


@pytest.mark.parametrize("role", ROLES_REFUSED, ids=lambda role: role.value)
def test_every_other_role_is_refused(
    call_route: Callable[..., Any], token_for: Callable[..., str], role: Role
) -> None:
    with pytest.raises(AuthorizationError):
        call_route(*INTERNAL_ONLY_ROUTE, token_for(role=role))


def test_no_token_is_refused_as_not_signed_in(call_route: Callable[..., Any]) -> None:
    with pytest.raises(AuthenticationError):
        call_route(*INTERNAL_ONLY_ROUTE, None)
