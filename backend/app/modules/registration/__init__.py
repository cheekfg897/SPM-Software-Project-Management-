"""Registration module — Attendees registering for confirmed events (SCRUM-52).

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.registration.services.count_registered`
"""

from __future__ import annotations

from flask import Flask


def register(app: Flask) -> None:
    """Attach the registration blueprint to ``app``."""
    from app.modules.registration.routes import bp

    app.register_blueprint(bp)
