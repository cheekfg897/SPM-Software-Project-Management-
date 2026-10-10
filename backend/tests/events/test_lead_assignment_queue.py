"""Unit tests for SCRUM-95 — the Event Coordinator Lead assigns each submitted request.

This file starts with AC7, the role itself: an account can be given the Event
Coordinator Lead role (ADR-0036).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.modules.auth.permissions import EXTERNAL_ROLES, INTERNAL_ROLES, Role, is_internal_role
from app.modules.auth.services import create_staff_user

pytestmark = pytest.mark.scrum_95


def test_the_lead_role_is_internal_staff() -> None:
    assert Role.EVENT_COORDINATOR_LEAD.value == "event_coordinator_lead"
    assert Role.EVENT_COORDINATOR_LEAD in INTERNAL_ROLES
    assert Role.EVENT_COORDINATOR_LEAD not in EXTERNAL_ROLES
    assert is_internal_role("event_coordinator_lead")


def test_a_staff_account_can_be_created_with_the_lead_role(
    mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    payload = {**valid_registration_payload, "role": Role.EVENT_COORDINATOR_LEAD.value}

    user = create_staff_user(payload, session=mock_session)

    assert user.role is Role.EVENT_COORDINATOR_LEAD
    mock_session.add.assert_called_once_with(user)
