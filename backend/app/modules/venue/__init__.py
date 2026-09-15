"""Venue module — venue catalogue, availability calendar, search, and the
setup/turnaround buffer times conflict detection depends on.

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.venue.services.get_venue`
"""

from __future__ import annotations

from flask import Flask


def register(app: Flask) -> None:
    """Attach the venue blueprint to ``app``."""
    from app.modules.venue.routes import bp

    app.register_blueprint(bp)
