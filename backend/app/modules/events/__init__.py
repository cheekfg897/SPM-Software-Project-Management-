"""Events module — event requests submitted by Event Organisers.

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.events.services.list_event_requests_for_organiser`
* :func:`app.modules.events.services.get_event_request_for_organiser`
"""

from __future__ import annotations

from flask import Flask


def register(app: Flask) -> None:
    """Attach the events blueprint to ``app``."""
    from app.modules.events.routes import bp

    app.register_blueprint(bp)
