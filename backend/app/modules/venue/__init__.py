"""Venue module — the venue catalogue.

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.venue.services.get_venue`
* :func:`app.modules.venue.services.check_venue_suitability` — reused by booking
  requests (SCRUM-42)
* :func:`app.modules.venue.services.list_booked_venues` — the venues an Attendee sees on
  their event's page (SCRUM-24 AC11)

Registers the ``flask expire-holds`` command, which the scheduled workflow runs to
expire tentative holds and warn coordinators before they do (SCRUM-94, ADR-0052).
"""

from __future__ import annotations

from flask import Flask


def register(app: Flask) -> None:
    """Attach the venue blueprint and CLI command to ``app``."""
    from app.modules.venue.commands import expire_holds_command
    from app.modules.venue.routes import bp

    app.register_blueprint(bp)
    app.cli.add_command(expire_holds_command)
