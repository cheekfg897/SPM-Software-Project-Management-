"""Database session helper shared by every module's services.

Service functions take an optional ``session`` so unit tests can pass a mock instead of
a real database session; this is the one place that decides which session to use.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.extensions import db


def resolve_session(session: Session | None) -> Session:
    """Return the explicit session if given, else the app-bound ``db.session``."""
    return session if session is not None else db.session
