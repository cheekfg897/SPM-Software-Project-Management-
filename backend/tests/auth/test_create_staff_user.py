"""Unit tests for SCRUM-88 — create a staff account through its own schema/service."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from werkzeug.security import check_password_hash

from app.common.errors import ConflictError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import EXTERNAL_ROLES, Role
from app.modules.auth.services import create_staff_user

pytestmark = pytest.mark.scrum_88


@pytest.fixture()
def staff_payload(valid_registration_payload: dict[str, Any]) -> dict[str, Any]:
    """A staff account body that satisfies every rule in ``CreateStaffUserSchema``."""
    return {**valid_registration_payload, "role": Role.VENUE_STAFF.value}


def test_each_staff_role_gets_an_account_with_a_hashed_password(
    staff_role: Role, mock_session: MagicMock, staff_payload: dict[str, Any]
) -> None:
    staff_payload["role"] = staff_role.value

    user = create_staff_user(staff_payload, session=mock_session)

    assert isinstance(user, User)
    assert user.role is staff_role
    assert user.email == "new.user@example.com"  # normalised
    assert user.full_name == "New User"
    assert user.organisation_id is None

    assert user.password_hash.startswith("scrypt:")
    assert check_password_hash(user.password_hash, staff_payload["password"])

    mock_session.add.assert_called_once_with(user)
    mock_session.commit.assert_called_once()


@pytest.mark.parametrize("role", sorted(role.value for role in EXTERNAL_ROLES))
def test_external_role_is_refused(
    role: str, mock_session: MagicMock, staff_payload: dict[str, Any]
) -> None:
    staff_payload["role"] = role

    with pytest.raises(ValidationError) as exc_info:
        create_staff_user(staff_payload, session=mock_session)

    err = exc_info.value
    assert err.status_code == 400
    assert err.details == {
        "role": [
            "Role must be one of: event_coordinator, event_coordinator_lead, "
            "technical_support_staff, venue_staff."
        ]
    }
    mock_session.add.assert_not_called()


def test_email_already_in_use_is_refused(
    mock_session: MagicMock, make_user: Callable[..., User], staff_payload: dict[str, Any]
) -> None:
    mock_session.scalar.return_value = make_user(email="new.user@example.com")

    with pytest.raises(ConflictError) as exc_info:
        create_staff_user(staff_payload, session=mock_session)

    assert exc_info.value.status_code == 409
    mock_session.add.assert_not_called()


def test_organisation_is_refused(mock_session: MagicMock, staff_payload: dict[str, Any]) -> None:
    staff_payload["organisation_id"] = 3

    with pytest.raises(ValidationError) as exc_info:
        create_staff_user(staff_payload, session=mock_session)

    assert exc_info.value.details == {"organisation_id": ["Unknown field."]}
