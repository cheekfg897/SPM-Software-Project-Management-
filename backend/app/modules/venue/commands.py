"""Flask CLI commands for the venue module.

A command stays thin, like a route: call a service, echo the result. The work happens
in ``services.py``, never here.
"""

from __future__ import annotations

import click
from flask.cli import with_appcontext

from app.modules.venue.services import expire_holds, send_hold_expiry_warnings


@click.command("expire-holds")
@with_appcontext
def expire_holds_command() -> None:
    """Expire the holds that have run out, then warn of those about to (SCRUM-94).

    The scheduled workflow runs it (ADR-0052). Expiring comes first, so a hold that has
    already run out gets the expiry notice rather than a warning. Both steps can run
    again without repeating anything, so a late or doubled run does no harm.
    """
    expired = expire_holds()
    warned = send_hold_expiry_warnings()
    click.echo(f"Expired {len(expired)} hold(s); warned about {len(warned)} hold(s).")
