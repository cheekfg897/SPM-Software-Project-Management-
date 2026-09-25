"""Business logic for the organisations module (SCRUM-66, ADR-0013).

These functions are the module's public API: routes call them, tests call them
directly, and other modules (auth, when an Event Organiser registers) call them
instead of touching :class:`~app.modules.organisations.models.ClientOrganisation`.
Every function takes an optional ``session``, defaulting to ``db.session``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.database import resolve_session
from app.common.errors import ConflictError, NotFoundError
from app.common.validation import load_or_raise
from app.modules.organisations.models import ClientOrganisation
from app.modules.organisations.schemas import CreateClientOrganisationSchema

#: Both the name check and the unique constraint answer with this (ADR-0013).
DUPLICATE_NAME_MESSAGE = "A client organisation with this name already exists."


def get_organisation(organisation_id: int, *, session: Session | None = None) -> ClientOrganisation:
    """Fetch a client organisation by primary key.

    Raises:
        NotFoundError: 404 — no such organisation.
    """
    organisation = resolve_session(session).get(ClientOrganisation, organisation_id)
    if organisation is None:
        raise NotFoundError("Client organisation not found.")
    return organisation


def list_organisations(*, session: Session | None = None) -> list[ClientOrganisation]:
    """Every client organisation, by name. Names are unique, so the order is stable."""
    stmt = select(ClientOrganisation).order_by(ClientOrganisation.name)
    return list(resolve_session(session).scalars(stmt))


def create_organisation(
    payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> ClientOrganisation:
    """Record a client organisation with its contact details (SCRUM-66 AC1).

    Args:
        payload: Decoded JSON body with ``name``, ``contact_name``, ``contact_email``
            and optional ``contact_phone``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The saved :class:`ClientOrganisation`.

    Raises:
        ValidationError: 400 — payload invalid (details per field).
        ConflictError: 409 — an organisation with the same name exists (ADR-0013).
    """
    data = load_or_raise(CreateClientOrganisationSchema(), payload)
    sess = resolve_session(session)

    existing = sess.scalar(
        select(ClientOrganisation).where(ClientOrganisation.name == data["name"])
    )
    if existing is not None:
        raise ConflictError(DUPLICATE_NAME_MESSAGE)

    organisation = ClientOrganisation(**data)
    sess.add(organisation)
    try:
        sess.commit()
    except IntegrityError as exc:
        # Race: another request saved the same name between our check and the
        # commit. The unique constraint is the real guarantee; answer with the same
        # 409 rather than a 500.
        sess.rollback()
        raise ConflictError(DUPLICATE_NAME_MESSAGE) from exc

    return organisation
