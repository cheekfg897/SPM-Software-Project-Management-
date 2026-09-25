"""Unit tests for SCRUM-66 AC4 — an event request belongs to an organisation.

It is the organiser's client organisation, copied from their account when they
submit and never taken from the request body. An organiser with no organisation
can't submit (ADR-0013).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.auth.services import register_user
from app.modules.events.models import EventRequest
from app.modules.events.services import OrganiserWithoutOrganisationError, submit_event_request
from app.modules.organisations.services import create_organisation

pytestmark = pytest.mark.scrum_66


def test_submission_is_linked_to_the_organisers_organisation(
    db_session: Session,
    valid_organisation_payload: dict[str, Any],
    organiser_registration_payload: Callable[[Any], dict[str, Any]],
    valid_event_request_payload: dict[str, Any],
    today: date,
) -> None:
    organisation = create_organisation(valid_organisation_payload, session=db_session)
    organiser = register_user(organiser_registration_payload(organisation.id), session=db_session)

    submitted = submit_event_request(
        str(organiser.id), valid_event_request_payload, session=db_session, today=today
    )

    db_session.expire_all()
    stored = db_session.get(EventRequest, submitted.id)
    assert stored is not None
    assert (stored.organiser_id, stored.organisation_id) == (organiser.id, organisation.id)


def test_organiser_without_an_organisation_cannot_submit(
    mock_session: MagicMock,
    make_user: Callable[..., User],
    valid_event_request_payload: dict[str, Any],
    today: date,
) -> None:
    """Organiser accounts from before SCRUM-66 have no organisation until linked."""
    mock_session.get.return_value = make_user(role=Role.EVENT_ORGANISER, user_id=7)

    with pytest.raises(OrganiserWithoutOrganisationError) as exc_info:
        submit_event_request("7", valid_event_request_payload, session=mock_session, today=today)

    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == "organiser_without_organisation"
    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()


def test_organisation_id_cannot_be_supplied_by_the_client(
    mock_session: MagicMock, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    """The organisation comes from the organiser's account; a client can't pick one."""
    valid_event_request_payload["organisation_id"] = 3

    with pytest.raises(ValidationError) as exc_info:
        submit_event_request("7", valid_event_request_payload, session=mock_session, today=today)

    assert exc_info.value.details == {"organisation_id": ["Unknown field."]}
    mock_session.add.assert_not_called()
