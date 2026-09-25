"""Venue module — the venue catalogue.

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.venue.services.get_venue`
"""

from __future__ import annotations

from flask import Flask


def register(app: Flask) -> None:
    """Attach the venue blueprint to ``app``."""
    from app.modules.venue.routes import bp

    app.register_blueprint(bp)
