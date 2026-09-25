"""Fixtures shared by the venue tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.modules.venue.models import Venue


@pytest.fixture()
def save(db_session: Session) -> Callable[..., None]:
    """Persist objects to ``db_session`` and commit, as a service would."""

    def _save(*objects: object) -> None:
        db_session.add_all(objects)
        db_session.commit()

    return _save


@pytest.fixture()
def reload_venue(db_session: Session) -> Callable[[int], Venue]:
    """Read a venue back from the database rather than from the session's cache."""

    def _reload(venue_id: int) -> Venue:
        db_session.expire_all()
        venue = db_session.get(Venue, venue_id)
        assert venue is not None
        return venue

    return _reload
