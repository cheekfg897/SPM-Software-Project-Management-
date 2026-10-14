"""Route protection decorators — the single place authorization is *enforced*.

Three decorators cover every case the system needs:

* :func:`requires_auth` — the caller must present a valid, unexpired JWT.
* :func:`requires_role` — as above, **and** the ``role`` claim in the token
  must be one of the allowed roles.
* :func:`optional_auth` — for a public route that still wants to know who is asking.

The first two produce the same JSON error shape via :mod:`app.common.errors`:
``401`` for missing/invalid/expired tokens, ``403`` for a valid token whose
role is not allowed. Failed attempts are logged with the role attempted, the
endpoint, and a timestamp (groundwork for the Auditability requirement).

Division of responsibility:

* ``common/decorators.py`` (this file) — the *mechanism*: verify token, read
  the role claim, compare against an allow-list, log, raise.
* ``modules/auth/permissions.py`` — the *policy vocabulary*: which roles
  exist and which groups they form (``INTERNAL_ROLES`` etc.).

``common`` never imports from ``app.modules``; feature modules import these
decorators plus the role constants they need from ``auth.permissions``.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TypeVar

from flask import g, request
from flask_jwt_extended import get_jwt, verify_jwt_in_request
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import PyJWTError

from app.common.errors import INVALID_TOKEN_MESSAGE, AuthenticationError, AuthorizationError

F = TypeVar("F", bound=Callable[..., Any])

#: Name of the JWT claim that carries the caller's role. Shared with the auth
#: service (which writes it) so the two can never drift apart.
ROLE_CLAIM = "role"

#: Dedicated logger so audit lines can be routed separately later on.
logger = logging.getLogger("connectsphere.authz")


def _role_value(role: Any) -> str | None:
    """Normalise an ``Enum`` member or plain string to its string value."""
    if role is None:
        return None
    if isinstance(role, Enum):
        return str(role.value)
    return str(role)


def normalise_roles(roles: Iterable[Any]) -> frozenset[str]:
    """Turn a mix of ``Enum`` members / strings into a set of role values."""
    return frozenset(v for v in (_role_value(r) for r in roles) if v is not None)


def log_authorization_failure(*, reason: str, role: str | None, detail: str = "") -> None:
    """Write a structured audit line for a failed authentication/authorization.

    Fields: reason, role attempted, endpoint, HTTP method, path, UTC timestamp.
    """
    logger.warning(
        "authz_failure reason=%s role=%s endpoint=%s method=%s path=%s timestamp=%s detail=%s",
        reason,
        role,
        request.endpoint,
        request.method,
        request.path,
        datetime.now(timezone.utc).isoformat(),
        detail,
    )


def authenticate_request() -> dict[str, Any]:
    """Verify the JWT on the current request and return its claims.

    Side effect: stores ``g.current_user_id`` and ``g.current_user_role`` so
    the route body can use them without decoding the token again.

    Raises:
        AuthenticationError: if the token is missing, malformed, has a bad
            signature, or has expired.
    """
    try:
        verify_jwt_in_request()
    except (JWTExtendedException, PyJWTError) as exc:
        log_authorization_failure(reason="invalid_token", role=None, detail=str(exc))
        raise AuthenticationError(INVALID_TOKEN_MESSAGE) from exc

    claims: dict[str, Any] = get_jwt()
    g.current_user_id = claims.get("sub")
    g.current_user_role = claims.get(ROLE_CLAIM)
    return claims


def requires_auth(func: F) -> F:
    """Protect a route so that only callers with a valid JWT may reach it.

    Example::

        @bp.get("/me")
        @requires_auth
        def me():
            ...
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        authenticate_request()
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def requires_role(*roles: Any) -> Callable[[F], F]:
    """Protect a route so that only the given role(s) may reach it.

    Implies :func:`requires_auth`. Accepts role ``Enum`` members or their
    string values (the value stored in the JWT ``role`` claim).

    Example::

        @bp.get("/internal-only")
        @requires_role(*INTERNAL_ROLES)
        def internal_only():
            ...

    Raises:
        ValueError: at decoration time if no roles are supplied — an empty
            allow-list would silently lock everyone out.
    """
    allowed = normalise_roles(roles)
    if not allowed:
        raise ValueError("requires_role() needs at least one role")

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            claims = authenticate_request()
            role = _role_value(claims.get(ROLE_CLAIM))
            if role not in allowed:
                log_authorization_failure(reason="forbidden_role", role=role)
                raise AuthorizationError("You do not have permission to perform this action.")
            return func(*args, **kwargs)

        # Exposed for introspection/tests: which roles this route allows.
        wrapper.allowed_roles = allowed  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def _claims_of_an_optional_token() -> dict[str, Any]:
    """The claims of the request's token, or none for a visitor or an invalid token."""
    try:
        verify_jwt_in_request()
    except (JWTExtendedException, PyJWTError):
        return {}
    return dict(get_jwt())


def optional_auth(func: F) -> F:
    """Let a route be reached with or without a token, and say who is asking.

    ``g.current_user_id`` and ``g.current_user_role`` hold the caller's, or ``None`` for
    a visitor. A token that is expired or invalid is read as a visitor, not refused, and
    isn't logged: the page is public, so there is nothing it failed to protect.

    Example::

        @bp.get("/catalogue")
        @optional_auth
        def catalogue():
            ...
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        claims = _claims_of_an_optional_token()
        g.current_user_id = claims.get("sub")
        g.current_user_role = claims.get(ROLE_CLAIM)
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
