"""Organisations module — the client organisations Event Organisers belong to.

SCRUM-66: internal users record client organisations, and an Event Organiser is
linked to one when they register (ADR-0013).

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.organisations.services.get_organisation`
* :func:`app.modules.organisations.services.create_organisation`
* :func:`app.modules.organisations.services.list_organisations`
"""

from __future__ import annotations

from flask import Flask


def register(app: Flask) -> None:
    """Attach the organisations blueprint to ``app``."""
    from app.modules.organisations.routes import bp

    app.register_blueprint(bp)
