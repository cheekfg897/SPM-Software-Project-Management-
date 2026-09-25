"""Unit tests for the application factory's logging setup (SCRUM-21 AC5).

Authorization failures are only "recorded" if their log lines reach the console exactly
once. Every ``create_app()`` shares the ``app`` logger, so the factory must not add a
second handler when another app is built in the same process.
"""

from __future__ import annotations

import pytest
from flask import Flask

from app import create_app

pytestmark = pytest.mark.scrum_21


def test_building_a_second_app_does_not_duplicate_log_handlers(app: Flask) -> None:
    handlers_before = list(app.logger.handlers)

    second_app = create_app("testing")

    assert len(handlers_before) == 1
    assert second_app.logger.handlers == handlers_before
