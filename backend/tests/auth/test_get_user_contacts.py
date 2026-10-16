"""Unit tests for SCRUM-55 "See who has registered for an event".

Showing who registered resolves each attendee's name and email in one query, without
the registration module touching the ``User`` model. Runs against ``db_session``, so
the lookup is real SQL.
"""

from __future__ import annotations

import pytest

from app.modules.auth.models import User
from app.modules.auth.services import UserContact, get_user_contacts

pytestmark = pytest.mark.scrum_55


def test_returns_every_known_users_name_and_email(saved_users: list[User]) -> None:
    assert get_user_contacts({3, 9}) == {
        3: UserContact(full_name="Coordinator Three", email="coordinator3@example.com"),
        9: UserContact(full_name="Coordinator Nine", email="coordinator9@example.com"),
    }


def test_an_id_with_no_matching_user_is_left_out(saved_users: list[User]) -> None:
    assert get_user_contacts([3, 99]) == {
        3: UserContact(full_name="Coordinator Three", email="coordinator3@example.com")
    }
