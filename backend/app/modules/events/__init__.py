"""Events module — event requests submitted by Event Organisers.

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.events.services.list_event_requests_for_organiser`
* :func:`app.modules.events.services.list_event_requests_for_coordinator`
* :func:`app.modules.events.services.get_event_request_for_organiser`
* :func:`app.modules.events.services.get_event_record_for_organiser`
* :func:`app.modules.events.services.list_equipment_requests_awaiting_action`
* :func:`app.modules.events.services.save_draft_event_request`
* :func:`app.modules.events.services.update_draft_event_request`
* :func:`app.modules.events.services.submit_draft_event_request`
* :func:`app.modules.events.services.update_event_request`
* :func:`app.modules.events.services.list_event_history`
* :func:`app.modules.events.services.list_unassigned_event_requests`
* :func:`app.modules.events.services.list_event_requests_with_equipment`
* :func:`app.modules.events.services.get_event_record_for_coordinator`
"""

from __future__ import annotations

from flask import Flask


def register(app: Flask) -> None:
    """Attach the events blueprint to ``app``."""
    from app.modules.events.routes import bp

    app.register_blueprint(bp)
