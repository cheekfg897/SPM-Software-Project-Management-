"""Venue module — the venue catalogue.

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.venue.services.get_venue`
* :func:`app.modules.venue.services.check_venue_suitability` — reused by booking
  requests (SCRUM-42)
"""

from __future__ import annotations

from flask import Flask


def register(app: Flask) -> None:
    """Attach the venue blueprint to ``app``."""
    from app.modules.venue.routes import bp

    app.register_blueprint(bp)
