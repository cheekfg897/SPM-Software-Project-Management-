"""Unit tests for SCRUM-88 — the ``flask create-staff-user`` CLI command."""

from __future__ import annotations

import pytest
from click.testing import Result
from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.auth.services import authenticate_user

pytestmark = pytest.mark.scrum_88


def _arguments(role: str) -> list[str]:
    """The command-line arguments for creating ``role``, everything but the password."""
    return [
        "create-staff-user",
        "--email",
        "New.Staff@Example.com",
        "--full-name",
        "New Staff",
        "--role",
        role,
    ]


def _typed_twice(password: str) -> str:
    """What a user types at the prompt: ``password``, then the same again to confirm."""
    return f"{password}\n{password}\n"


def _run(app: Flask, role: str, typed: str) -> Result:
    """Run ``create-staff-user``, typing ``typed`` at the password prompt."""
    runner = app.test_cli_runner()
    return runner.invoke(args=_arguments(role), input=typed)


def _users(db_session: Session) -> list[User]:
    """Every user currently saved to ``db_session``."""
    return list(db_session.scalars(select(User)))


def _assert_refused(result: Result, expected_line: str, db_session: Session) -> None:
    """The command failed, said ``expected_line``, and saved nobody."""
    assert result.exit_code == 1
    assert "Error: Invalid request." in result.output
    assert expected_line in result.output
    assert _users(db_session) == []


def test_command_creates_a_staff_account_that_can_log_in(
    app: Flask, staff_role: Role, db_session: Session, valid_password: str
) -> None:
    result = _run(app, staff_role.value, _typed_twice(valid_password))

    assert result.exit_code == 0
    assert f"Created {staff_role.value} account for new.staff@example.com" in result.output
    assert valid_password not in result.output

    logged_in = authenticate_user("new.staff@example.com", valid_password, session=db_session)
    assert logged_in.user.role is staff_role


def test_command_refuses_an_external_role_and_saves_nothing(
    app: Flask, db_session: Session, valid_password: str
) -> None:
    result = _run(app, Role.ATTENDEE.value, _typed_twice(valid_password))

    _assert_refused(result, "role: Role must be one of:", db_session)


def test_command_refuses_a_weak_password_and_saves_nothing(app: Flask, db_session: Session) -> None:
    # Breaks only the "at least one digit" rule, so the error names that one rule.
    result = _run(app, Role.VENUE_STAFF.value, _typed_twice("abcdefgh"))

    _assert_refused(result, "password: Password must contain at least one digit.", db_session)


def test_command_refuses_an_email_already_in_use(
    app: Flask, db_session: Session, valid_password: str
) -> None:
    first = _run(app, Role.VENUE_STAFF.value, _typed_twice(valid_password))
    assert first.exit_code == 0

    second = _run(app, Role.VENUE_STAFF.value, _typed_twice(valid_password))

    assert second.exit_code == 1
    assert "Error: An account with this email already exists." in second.output
    assert len(_users(db_session)) == 1


def test_password_must_be_typed_the_same_twice(
    app: Flask, db_session: Session, valid_password: str
) -> None:
    # Click re-prompts on a mismatch; with no third line of input left to read, it
    # aborts rather than looping forever.
    result = _run(app, Role.VENUE_STAFF.value, typed=f"{valid_password}\nDifferent1\n")

    assert result.exit_code == 1
    assert "Error: The two entered values do not match." in result.output
    assert "Aborted!" in result.output
    assert _users(db_session) == []


def test_password_cannot_be_given_as_an_option(app: Flask) -> None:
    runner = app.test_cli_runner()

    result = runner.invoke(args=[*_arguments(Role.VENUE_STAFF.value), "--password", "x"])

    assert result.exit_code == 2
    assert "No such option" in result.output
