"""Unit tests for the shared invalid-token response (SCRUM-21 AC5: refused requests).

Flask-JWT-Extended calls its error callbacks with either the error text or the token's
header and payload. One function serves every callback, so it is exercised with both.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.common.errors import invalid_token_response

pytestmark = pytest.mark.scrum_21


@pytest.mark.parametrize(
    "callback_args",
    [("Missing Authorization Header",), ({"alg": "HS256"}, {"sub": "7"})],
)
def test_invalid_token_response_uses_the_project_error_shape(
    callback_args: tuple[Any, ...],
) -> None:
    response, status = invalid_token_response(*callback_args)

    assert status == 401
    assert response.get_json() == {
        "error": "authentication_error",
        "message": "Missing, invalid or expired token.",
    }
