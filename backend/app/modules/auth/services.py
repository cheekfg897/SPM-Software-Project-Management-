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

from app.common.decorators import ROLE_CLAIM
from app.common.errors import AuthenticationError, ConflictError, NotFoundError
from app.common.validation import load_or_raise
from app.extensions import db
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.auth.schemas import RegisterSchema

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


def _session(session: Session | None) -> Session:
    """Return the explicit session if given, else the app-bound one."""
    return session if session is not None else db.session


def normalise_email(email: str) -> str:
    """Canonicalise an email for storage/lookup (trimmed, lower-cased)."""
    return email.strip().lower()


def get_user_by_email(email: str, *, session: Session | None = None) -> User | None:
    """Fetch a user by (normalised) email, or ``None`` if not found."""
    stmt = select(User).where(User.email == normalise_email(email))
    return _session(session).scalar(stmt)


def get_user_by_id(user_id: int | str, *, session: Session | None = None) -> User:
    """Fetch a user by primary key.

    Raises:
        NotFoundError: if no such user exists.
    """
    user = _session(session).get(User, int(user_id))
    if user is None:
        raise NotFoundError("User not found.")
    return user


def register_user(payload: Mapping[str, Any] | None, *, session: Session | None = None) -> User:
    """Create a new account (SCRUM-65).

    Validates the payload against :class:`RegisterSchema` (required fields,
    email format, role, password policy), checks the email is not already in
    use, hashes the password and persists the user.

    Args:
        payload: Decoded JSON body with ``email``, ``password``, ``full_name``,
            ``role`` and optional ``organisation``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The persisted :class:`User`. Its ``password_hash`` is set, the
        plaintext password is not retained anywhere on the object.

    Raises:
        ValidationError: 400 — payload invalid (details per field).
        ConflictError: 409 — email already registered.
    """
    data = load_or_raise(RegisterSchema(), payload)
    sess = _session(session)

    email = normalise_email(data["email"])
    if get_user_by_email(email, session=sess) is not None:
        raise ConflictError("An account with this email already exists.")

    user = User(
        email=email,
        full_name=data["full_name"].strip(),
        role=Role.from_value(data["role"]),
        organisation=(data.get("organisation") or None),
    )
    user.set_password(data["password"])

    sess.add(user)
    try:
        sess.commit()
    except IntegrityError as exc:
        # Race: another request inserted the same email between our check and
        # the commit. The DB unique index is the real guarantee; translate it
        # into the same 409 rather than a 500.
        sess.rollback()
        raise ConflictError("An account with this email already exists.") from exc

    return user


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


def issue_access_token(user: User) -> str:
    """Create a JWT for ``user`` with the ``role`` claim the decorators expect.

    Expiry comes from ``JWT_ACCESS_TOKEN_EXPIRES`` (default 1 hour).
    """
    # TODO: refresh tokens are a future story — when added, issue them here
    # alongside the access token and add a /api/auth/refresh route.
    role_value = user.role.value if isinstance(user.role, Role) else str(user.role)
    return create_access_token(
        identity=str(user.id),
        additional_claims={ROLE_CLAIM: role_value},
    )
