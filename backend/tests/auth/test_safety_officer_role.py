"""Unit tests for SCRUM-97 AC7 "A user account can be given the Safety Officer role".

The Safety Officer is internal staff, so the account is created the way every staff
account is: ``flask create-staff-user`` through ``create_staff_user`` (ADR-0023,
ADR-0047).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.modules.auth.permissions import Role, is_internal_role
from app.modules.auth.services import create_staff_user

pytestmark = pytest.mark.scrum_97


def test_the_safety_officer_is_an_internal_role() -> None:
    assert Role.from_value("safety_officer") is Role.SAFETY_OFFICER
    assert is_internal_role(Role.SAFETY_OFFICER) is True


def test_a_staff_account_can_be_given_the_safety_officer_role(
    mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    payload = {**valid_registration_payload, "role": "safety_officer"}

    user = create_staff_user(payload, session=mock_session)

    assert user.role is Role.SAFETY_OFFICER
    mock_session.add.assert_called_once_with(user)
