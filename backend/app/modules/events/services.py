"""Business logic for the events module.

These functions are the module's public API: routes call them, tests call
them directly, and future modules that need event request data call them
instead of touching :class:`~app.modules.events.models.EventRequest`.

Every function takes an optional ``session`` so unit tests can pass a mock
instead of a real database session. In production the default
``db.session`` is used.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.database import resolve_session
from app.common.errors import AppError
from app.common.validation import load_or_raise
from app.modules.events.models import (
    REFERENCE_UNIQUE_CONSTRAINT,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.schemas import SubmitEventRequestSchema

logger = logging.getLogger("connectsphere.events")

# Reference format (ADR-0004): "EVR-" + 8 characters with no look-alikes (0 O 1 I L).
REFERENCE_PREFIX = "EVR-"
REFERENCE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
REFERENCE_LENGTH = 8
MAX_REFERENCE_ATTEMPTS = 3


class ReferenceGenerationError(AppError):
    """No unused reference was found after several attempts (500)."""

    status_code = 500
    error_code = "reference_generation_failed"


def generate_reference() -> str:
    """Return a random reference such as ``EVR-7K2QX9AB``."""
    return REFERENCE_PREFIX + "".join(
        secrets.choice(REFERENCE_ALPHABET) for _ in range(REFERENCE_LENGTH)
    )


def is_reference_collision(exc: IntegrityError) -> bool:
    """Return ``True`` if ``exc`` was caused by the unique constraint on ``reference``.

    PostgreSQL (psycopg2) reports the violated constraint on ``orig.diag``.
    Drivers without that (e.g. SQLite) only give a message, so fall back to it.
    """
    diag = getattr(exc.orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    if constraint is not None:
        return constraint == REFERENCE_UNIQUE_CONSTRAINT
    message = str(exc.orig)
    return REFERENCE_UNIQUE_CONSTRAINT in message or "event_requests.reference" in message


def submit_event_request(
    organiser_id: int | str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
    today: date | None = None,
    reference_factory: Callable[[], str] = generate_reference,
) -> EventRequest:
    """Submit a new event request on behalf of an organiser (SCRUM-19).

    Validates the payload (AC1-AC4), then saves it with status ``submitted``
    and a fresh reference (AC5). If the reference is already taken, the save
    is rolled back and retried with a new one, up to
    :data:`MAX_REFERENCE_ATTEMPTS` times.

    Args:
        organiser_id: The caller's user id, taken from their token.
        payload: Decoded JSON body.
        session: Database session; defaults to ``db.session``.
        today: Reference date for the "not in the past" rule; defaults to
            today in the business timezone.
        reference_factory: Makes references; tests swap it out.

    Returns:
        The saved :class:`EventRequest`.

    Raises:
        ValidationError: 400 — payload invalid (details per field).
        ReferenceGenerationError: 500 — every attempt hit a used reference.
        IntegrityError: any other constraint failure; not retried.
    """
    data = load_or_raise(SubmitEventRequestSchema(today=today), payload)
    sess = resolve_session(session)

    for attempt in range(1, MAX_REFERENCE_ATTEMPTS + 1):
        event_request = EventRequest(
            organiser_id=int(organiser_id),
            reference=reference_factory(),
            status=EventRequestStatus.SUBMITTED,
            **data,
        )
        sess.add(event_request)
        try:
            sess.commit()
        except IntegrityError as exc:
            sess.rollback()
            if not is_reference_collision(exc):
                raise
            logger.warning(
                "event_request_reference_collision reference=%s attempt=%d",
                event_request.reference,
                attempt,
            )
            continue
        return event_request

    raise ReferenceGenerationError("Could not create the event request. Please try again.")


def list_event_requests_for_organiser(
    organiser_id: int | str, *, session: Session | None = None
) -> list[EventRequest]:
    """Return the organiser's own event requests, newest first (SCRUM-19 AC5)."""
    stmt = (
        select(EventRequest)
        .where(EventRequest.organiser_id == int(organiser_id))
        .order_by(EventRequest.created_at.desc(), EventRequest.id.desc())
    )
    return list(resolve_session(session).scalars(stmt))
