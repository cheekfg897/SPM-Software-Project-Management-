"""Unit tests for the application factory's logging setup (SCRUM-21 AC5, SCRUM-89).

Authorization failures and logouts are only "recorded" if their log lines reach the
console exactly once (ADR-0007, ADR-0110). Every ``create_app()`` shares the ``app`` and
``connectsphere`` loggers, so the factory must not add a second handler when another app
is built in the same process.
"""

from __future__ import annotations

import logging

import pytest
from flask import Flask

from app import create_app

pytestmark = pytest.mark.scrum_21


def test_building_a_second_app_does_not_duplicate_log_handlers(app: Flask) -> None:
    handlers_before = list(app.logger.handlers)

    second_app = create_app("testing")

    assert len(handlers_before) == 1
    assert second_app.logger.handlers == handlers_before


@pytest.mark.scrum_89
def test_info_lines_of_the_connectsphere_loggers_reach_one_console_handler(app: Flask) -> None:
    create_app("testing")

    [handler] = logging.getLogger("connectsphere").handlers

    assert isinstance(handler, logging.StreamHandler)
    assert logging.getLogger("connectsphere.authz").isEnabledFor(logging.INFO)
