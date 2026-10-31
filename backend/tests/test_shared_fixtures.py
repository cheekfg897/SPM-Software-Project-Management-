"""Unit tests for the suite's shared ``make_user`` factory (SCRUM-5).

Werkzeug's scrypt is slow on purpose, and hashing the same password for every user
took almost 90% of the suite's time, enough to push CI past its 15-minute limit. The
factory hashes each password once, so these check that its users still sign in with it.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.modules.auth.models import User

pytestmark = pytest.mark.scrum_5


def test_users_made_with_the_same_password_share_one_hash(
    make_user: Callable[..., User],
) -> None:
    first = make_user(email="first@example.com")
    second = make_user(email="second@example.com")

    assert first.password_hash == second.password_hash
    assert first.password_hash.startswith("scrypt:")


def test_a_made_user_signs_in_with_their_password_and_no_other(
    make_user: Callable[..., User],
) -> None:
    user = make_user(password="Another-Password-9")

    assert user.check_password("Another-Password-9")
    assert not user.check_password("Password123")
