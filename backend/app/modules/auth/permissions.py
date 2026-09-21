"""Permission *policy* for the auth module: roles and role groups.

Enforcement (token verification, allow-list comparison, logging, error
responses) lives in :mod:`app.common.decorators`. This file only defines the
vocabulary those decorators are fed, so that "who counts as internal staff"
is decided in exactly one place. Feature modules added in later sprints should
import these constants rather than spelling role strings out by hand.
"""

from __future__ import annotations

import enum


class Role(str, enum.Enum):
    """The five user roles of the system.

    Inherits from ``str`` so members compare equal to their string value and
    serialise cleanly into JSON / JWT claims.
    """

    EVENT_ORGANISER = "event_organiser"  # external — client rep who requests events
    ATTENDEE = "attendee"  # external — registers for events
    EVENT_COORDINATOR = "event_coordinator"  # internal — coordinates event planning
    VENUE_STAFF = "venue_staff"  # internal — manages venues and bookings
    TECHNICAL_SUPPORT_STAFF = "technical_support_staff"  # internal — equipment / tech support

    @classmethod
    def values(cls) -> list[str]:
        """All role values as plain strings (used by validation schemas)."""
        return [member.value for member in cls]

    @classmethod
    def from_value(cls, value: str) -> Role:
        """Look up a member by its string value.

        Raises:
            ValueError: if ``value`` is not a known role.
        """
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"Unknown role: {value!r}") from exc


#: Roles that belong to ConnectSphere staff.
INTERNAL_ROLES: frozenset[Role] = frozenset(
    {Role.EVENT_COORDINATOR, Role.VENUE_STAFF, Role.TECHNICAL_SUPPORT_STAFF}
)

#: Roles that belong to external users (clients and the public).
EXTERNAL_ROLES: frozenset[Role] = frozenset({Role.EVENT_ORGANISER, Role.ATTENDEE})

#: Every role. Useful for "any authenticated user" allow-lists where
#: ``requires_auth`` is not expressive enough (e.g. documentation).
ALL_ROLES: frozenset[Role] = INTERNAL_ROLES | EXTERNAL_ROLES


def is_internal_role(role: Role | str) -> bool:
    """Return ``True`` if ``role`` is one of the internal staff roles."""
    try:
        return Role(role) in INTERNAL_ROLES
    except ValueError:
        return False


def is_external_role(role: Role | str) -> bool:
    """Return ``True`` if ``role`` is one of the external roles."""
    try:
        return Role(role) in EXTERNAL_ROLES
    except ValueError:
        return False
