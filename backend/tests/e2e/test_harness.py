"""Smoke tests for the end-to-end harness in ``tests/e2e/conftest.py`` (SCRUM-41).

They prove the harness before a journey relies on it: ``sign_in`` logs a real user in
over ``POST /api/auth/login``, the :class:`Actor` it returns is authenticated by its
token and nothing else, and a request reads and writes the same database as
``db_session`` (ADR-0031).
"""

from __future__ import annotations

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.notifications.models import Notification
from app.modules.notifications.services import EventSummary, NotificationKind, notify_users
from tests.e2e.actors import Actor, SignIn

pytestmark = [pytest.mark.scrum_41, pytest.mark.e2e]

#: The Event Organiser saved by ``saved_users``, with ``make_user``'s default password.
ORGANISER_ID = 7
ORGANISER_EMAIL = "organiser7@example.com"
PASSWORD = "Password123"

#: Any signed-in user may read their own profile, so it shows whose token was sent.
PROFILE_PATH = "/api/auth/me"


@pytest.fixture()
def organiser(saved_users: list[User], sign_in: SignIn) -> Actor:
    """The saved Event Organiser, signed in over HTTP."""
    return sign_in(ORGANISER_EMAIL, PASSWORD)


def test_a_signed_in_actor_is_recognised_as_their_user(organiser: Actor) -> None:
    response = organiser.get(PROFILE_PATH)

    assert response.status_code == 200
    assert response.get_json()["email"] == ORGANISER_EMAIL


def test_only_the_actors_token_authenticates_their_requests(
    organiser: Actor, client: FlaskClient
) -> None:
    with_token = organiser.get(PROFILE_PATH)
    without_token = client.get(PROFILE_PATH)

    assert (with_token.status_code, without_token.status_code) == (200, 401)


def test_a_request_and_db_session_share_one_database(organiser: Actor, db_session: Session) -> None:
    event = EventSummary(id=1, reference="EVR-AAAAAAAA", name="Partner Summit")
    [notification] = notify_users(
        [ORGANISER_ID], event, NotificationKind.COORDINATOR_ASSIGNED, session=db_session
    )

    response = organiser.post(f"/api/notifications/{notification.id}/read")
    # Read it back from the database, not from the session's cache.
    db_session.expire_all()
    saved = db_session.get(Notification, notification.id)

    assert response.status_code == 200
    assert saved is not None
    assert saved.read_at is not None
