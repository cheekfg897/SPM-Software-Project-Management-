"""Flask CLI commands for the auth module.

A command stays thin, like a route: turn its options into a payload, call a service,
echo the result. Validation and database access happen in ``services.py``, never here.
"""

from __future__ import annotations

import click
from flask.cli import with_appcontext

from app.common.errors import AppError
from app.modules.auth.permissions import INTERNAL_ROLES
from app.modules.auth.services import create_staff_user

_STAFF_ROLE_CHOICES = ", ".join(sorted(role.value for role in INTERNAL_ROLES))


def _describe(error: AppError) -> str:
    """Render an ``AppError`` as the text ``click.ClickException`` shows.

    One line for the error's own message, then one "field: message" line per
    validation detail, so an invalid ``--role`` or a weak password says exactly
    what to fix.
    """
    lines = [error.message]
    for field, messages in (error.details or {}).items():
        for message in messages:
            lines.append(f"{field}: {message}")
    return "\n".join(lines)


@click.command("create-staff-user")
@click.option("--email", required=True, help="The new account's email address.")
@click.option("--full-name", required=True, help="The new account's full name.")
@click.option("--role", required=True, help=f"One of: {_STAFF_ROLE_CHOICES}.")
@with_appcontext
def create_staff_user_command(email: str, full_name: str, role: str) -> None:
    """Create an internal staff account (SCRUM-88, ADR-0023).

    Staff accounts are provisioned this way, by whoever operates the deployment,
    rather than through the public register route (ADR-0023). The password is
    prompted for twice, hidden, so it never appears in shell history or a process
    listing; there is deliberately no ``--password`` option.
    """
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)

    try:
        user = create_staff_user(
            {"email": email, "full_name": full_name, "role": role, "password": password}
        )
    except AppError as exc:
        raise click.ClickException(_describe(exc)) from exc

    click.echo(f"Created {user.role.value} account for {user.email} (id {user.id}).")
