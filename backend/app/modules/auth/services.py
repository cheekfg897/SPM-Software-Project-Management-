"""Business logic for the auth module.

These functions are the module's public API: routes call them, tests call
them directly, and future modules that need user data call them instead of
touching :class:`~app.modules.auth.models.User`.

Every function takes an optional ``session`` so unit tests can pass a mock
instead of a real database session. In production the default
``db.session`` is used.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from flask_jwt_extended import create_access_token
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from app.common.database import resolve_session
from app.common.decorators import ROLE_CLAIM
from app.common.errors import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.common.validation import load_or_raise
from app.modules.auth.models import User
from app.modules.auth.permissions import Role, role_value
from app.modules.auth.schemas import CreateStaffUserSchema, RegisterSchema
from app.modules.organisations.services import get_organisation

#: The one message used for *every* login failure so that responses cannot be
#: used to discover which emails are registered.
INVALID_CREDENTIALS_MESSAGE = "Invalid email or password."

#: A throwaway hash used to keep the "unknown email" path roughly the same
#: cost as the "wrong password" path (defence against timing-based enumeration).
_DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-password-0")


@dataclass(frozen=True)
class AuthResult:
    """What a successful login returns."""

    access_token: str
    user: User


def normalise_email(email: str) -> str:
    """Canonicalise an email for storage/lookup (trimmed, lower-cased)."""
    return email.strip().lower()


def get_user_by_email(email: str, *, session: Session | None = None) -> User | None:
    """Fetch a user by (normalised) email, or ``None`` if not found."""
    stmt = select(User).where(User.email == normalise_email(email))
    return resolve_session(session).scalar(stmt)


def get_user_by_id(user_id: int | str, *, session: Session | None = None) -> User:
    """Fetch a user by primary key.

    Raises:
        NotFoundError: if no such user exists.
    """
    user = resolve_session(session).get(User, int(user_id))
    if user is None:
        raise NotFoundError("User not found.")
    return user


def _check_organisation_exists(organisation_id: int, session: Session) -> None:
    """Refuse an unknown client organisation as a 400 on its field (SCRUM-66 AC2).

    It is a bad value in the payload, like any other, rather than a missing resource.
    """
    try:
        get_organisation(organisation_id, session=session)
    except NotFoundError as exc:
        raise ValidationError(
            "Invalid request.", details={"organisation_id": [exc.message]}
        ) from exc


def list_user_ids_with_role(role: Role, *, session: Session | None = None) -> list[int]:
    """Return the id of every user with ``role``, lowest id first (SCRUM-28 AC3).

    Ids rather than users, so nothing of :class:`User` crosses the module boundary.
    """
    stmt = select(User.id).where(User.role == role).order_by(User.id)
    return list(resolve_session(session).scalars(stmt))


def _save_new_user(data: Mapping[str, Any], session: Session) -> User:
    """Hash the password and persist a new account from already-validated ``data``.

    Shared by :func:`register_user` and :func:`create_staff_user` (SCRUM-88): both
    validate the payload against their own schema first, then save it the same way.

    Raises:
        ConflictError: 409 — email already registered.
    """
    email = normalise_email(data["email"])
    if get_user_by_email(email, session=session) is not None:
        raise ConflictError("An account with this email already exists.")

    user = User(
        email=email,
        full_name=data["full_name"].strip(),
        # Only an Event Organiser's registration payload carries this (ADR-0013);
        # CreateStaffUserSchema has no such field, so it is always None there.
        organisation_id=data.get("organisation_id"),
        role=Role.from_value(data["role"]),
    )
    user.set_password(data["password"])

    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        # Race: another request inserted the same email between our check and
        # the commit. The DB unique index is the real guarantee; translate it
        # into the same 409 rather than a 500.
        session.rollback()
        raise ConflictError("An account with this email already exists.") from exc

    return user


def register_user(payload: Mapping[str, Any] | None, *, session: Session | None = None) -> User:
    """Create a new account (SCRUM-65).

    Validates the payload against :class:`RegisterSchema` (required fields,
    email format, role, password policy), checks that an Event Organiser's
    client organisation exists (SCRUM-66), checks the email is not already in
    use, hashes the password and persists the user.

    Args:
        payload: Decoded JSON body with ``email``, ``password``, ``full_name``,
            ``role`` and, for an Event Organiser only, ``organisation_id``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The persisted :class:`User`. Its ``password_hash`` is set, the
        plaintext password is not retained anywhere on the object.

    Raises:
        ValidationError: 400 — payload invalid (details per field), including an
            organisation id that is missing, not allowed for the role, or unknown.
        ConflictError: 409 — email already registered.
    """
    data = load_or_raise(RegisterSchema(), payload)
    sess = resolve_session(session)

    organisation_id = data["organisation_id"]
    if organisation_id is not None:
        _check_organisation_exists(organisation_id, sess)

    return _save_new_user(data, sess)


def create_staff_user(payload: Mapping[str, Any] | None, *, session: Session | None = None) -> User:
    """Create an internal staff account (SCRUM-88, ADR-0023).

    Called by the ``flask create-staff-user`` command, never by a public route: staff
    are provisioned by whoever operates the deployment, not by self-registration.
    Validates the payload against :class:`CreateStaffUserSchema` (required fields,
    email format, an internal role, password policy), checks the email is not already
    in use, hashes the password and persists the user the same way
    :func:`register_user` does.

    Args:
        payload: ``email``, ``password``, ``full_name`` and ``role``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The persisted :class:`User`.

    Raises:
        ValidationError: 400 — payload invalid (details per field), including a role
            that is not one of the internal staff roles.
        ConflictError: 409 — email already registered.
    """
    data = load_or_raise(CreateStaffUserSchema(), payload)
    return _save_new_user(data, resolve_session(session))


def issue_access_token(user: User) -> str:
    """Create a JWT for ``user`` with the ``role`` claim the decorators expect.

    Expiry comes from ``JWT_ACCESS_TOKEN_EXPIRES`` (default 1 hour).
    """
    # TODO: refresh tokens are a future story — when added, issue them here
    # alongside the access token and add a /api/auth/refresh route.
    return create_access_token(
        identity=str(user.id),
        additional_claims={ROLE_CLAIM: role_value(user.role)},
    )


def authenticate_user(email: str, password: str, *, session: Session | None = None) -> AuthResult:
    """Verify credentials and issue an access token (SCRUM-6).

    Args:
        email: The login email (case-insensitive).
        password: The plaintext password to check.
        session: Database session; defaults to ``db.session``.

    Returns:
        :class:`AuthResult` with a JWT access token and the user.

    Raises:
        AuthenticationError: 401 with :data:`INVALID_CREDENTIALS_MESSAGE` for
            **both** an unknown email and a wrong password.
    """
    user = get_user_by_email(email, session=session) if email else None

    if user is None:
        # Burn roughly the same time as a real hash check, then fail generically.
        check_password_hash(_DUMMY_PASSWORD_HASH, password or "")
        raise AuthenticationError(INVALID_CREDENTIALS_MESSAGE)

    if not user.check_password(password or ""):
        raise AuthenticationError(INVALID_CREDENTIALS_MESSAGE)

    return AuthResult(access_token=issue_access_token(user), user=user)
