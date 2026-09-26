"""Unit tests for SCRUM-33 "Update event information and flag significant changes".

Showing an event's history resolves actor and coordinator names from the ids stored
on it, in one query rather than one ``get_user_by_id`` per entry (ADR-0025).
Runs against ``db_session``, so the lookup is real SQL.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.services import get_user_full_names

pytestmark = pytest.mark.scrum_33


def test_returns_every_known_users_full_name(saved_users: list[User]) -> None:
    assert get_user_full_names({3, 9}) == {3: "Coordinator Three", 9: "Coordinator Nine"}


def test_an_id_with_no_matching_user_is_left_out(saved_users: list[User]) -> None:
    assert get_user_full_names([3, 99]) == {3: "Coordinator Three"}


def test_no_ids_returns_an_empty_mapping(db_session: Session) -> None:
    assert get_user_full_names([]) == {}
