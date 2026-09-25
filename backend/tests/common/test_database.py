"""Unit tests for :func:`app.common.database.resolve_session`.

Every service resolves its database session through this helper, so it is tagged with
the stories whose services depend on it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.common.database import resolve_session
from app.extensions import db

pytestmark = [pytest.mark.scrum_6, pytest.mark.scrum_19, pytest.mark.scrum_65]


def test_an_explicit_session_is_used_as_given(mock_session: MagicMock) -> None:
    assert resolve_session(mock_session) is mock_session


def test_no_session_falls_back_to_the_app_bound_session() -> None:
    assert resolve_session(None) is db.session
