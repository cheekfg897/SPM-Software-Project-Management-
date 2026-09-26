"""Unit tests for SCRUM-65/SCRUM-88 — only external roles self-register (ADR-0023)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.common.errors import ValidationError
from app.modules.auth.permissions import Role
from app.modules.auth.services import register_user

pytestmark = [pytest.mark.scrum_65, pytest.mark.scrum_88]


def test_staff_role_cannot_self_register(
    staff_role: Role, mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    valid_registration_payload["role"] = staff_role.value

    with pytest.raises(ValidationError) as exc_info:
        register_user(valid_registration_payload, session=mock_session)

    err = exc_info.value
    assert err.status_code == 400
    assert err.error_code == "validation_error"
    assert err.details == {"role": ["Role must be one of: attendee, event_organiser."]}
    mock_session.add.assert_not_called()
