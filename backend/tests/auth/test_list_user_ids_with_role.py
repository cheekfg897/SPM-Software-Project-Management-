"""Unit tests for SCRUM-28 "Receive notifications about my events": users by role.

Covers what AC3 needs from the auth module: the ids of every user with a role, so the
events module can notify every Event Coordinator without importing ``User``. Runs
against ``db_session``, so the role filter and the ordering are real SQL.
"""

from __future__ import annotations

import pytest

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.auth.services import list_user_ids_with_role

pytestmark = pytest.mark.scrum_28


# --------------------------------------------------------------------------
# AC3 — every user with the role, lowest id first
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "expected_ids"),
    [
        (Role.EVENT_COORDINATOR, [3, 9]),
        (Role.VENUE_STAFF, [4]),
        (Role.ATTENDEE, []),
    ],
    ids=["event_coordinator", "venue_staff", "attendee"],
)
def test_lists_the_ids_of_every_user_with_the_role_lowest_first(
    saved_users: list[User], role: Role, expected_ids: list[int]
) -> None:
    assert list_user_ids_with_role(role) == expected_ids
