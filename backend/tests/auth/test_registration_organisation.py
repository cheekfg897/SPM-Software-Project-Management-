"""Unit tests for SCRUM-66 AC2 and AC3 — Event Organisers belong to an organisation.

An Event Organiser registers with the id of an existing client organisation; no other
role may send one (ADR-0013). Runs against ``db_session`` so the organisation lookup
really executes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.auth.schemas import UserSchema
from app.modules.auth.services import register_user
from app.modules.organisations.models import ClientOrganisation
from app.modules.organisations.services import create_organisation

pytestmark = pytest.mark.scrum_66

OrganiserPayload = Callable[[Any], dict[str, Any]]

NON_ORGANISER_ROLES = sorted(ALL_ROLES - {Role.EVENT_ORGANISER}, key=lambda r: r.value)


@pytest.fixture()
def organisation(
    db_session: Session, valid_organisation_payload: dict[str, Any]
) -> ClientOrganisation:
    """A saved client organisation for organisers to register into."""
    return create_organisation(valid_organisation_payload, session=db_session)


def _rejected_details(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Register with ``payload``; expect a 400 and no user saved. Return the details."""
    with pytest.raises(ValidationError) as exc_info:
        register_user(payload, session=session)

    assert exc_info.value.status_code == 400
    assert list(session.scalars(select(User))) == []
    return exc_info.value.details or {}


# --------------------------------------------------------------------------
# AC2 — an Event Organiser is associated with exactly one client organisation
# --------------------------------------------------------------------------


def test_organiser_registers_with_an_existing_organisation(
    db_session: Session,
    organisation: ClientOrganisation,
    organiser_registration_payload: OrganiserPayload,
) -> None:
    user = register_user(organiser_registration_payload(organisation.id), session=db_session)

    db_session.expire_all()
    stored = db_session.get(User, user.id)
    assert stored is not None
    assert stored.organisation_id == organisation.id
    dumped = UserSchema().dump(stored)
    assert dumped["organisation_id"] == organisation.id
    assert "organisation" not in dumped


@pytest.mark.parametrize("leave_out", [True, False], ids=["missing", "null"])
def test_organiser_without_an_organisation_is_rejected(
    db_session: Session, leave_out: bool, organiser_registration_payload: OrganiserPayload
) -> None:
    payload = organiser_registration_payload(None)
    if leave_out:
        del payload["organisation_id"]

    assert _rejected_details(db_session, payload) == {
        "organisation_id": ["Event Organisers must belong to a client organisation."]
    }


def test_unknown_organisation_is_rejected(
    db_session: Session, organiser_registration_payload: OrganiserPayload
) -> None:
    assert _rejected_details(db_session, organiser_registration_payload(999)) == {
        "organisation_id": ["Client organisation not found."]
    }


@pytest.mark.parametrize("role", NON_ORGANISER_ROLES, ids=lambda r: r.value)
def test_non_organiser_with_an_organisation_is_rejected(
    db_session: Session,
    role: Role,
    organisation: ClientOrganisation,
    organiser_registration_payload: OrganiserPayload,
) -> None:
    payload = {**organiser_registration_payload(organisation.id), "role": role.value}

    assert _rejected_details(db_session, payload) == {
        "organisation_id": ["Only Event Organisers belong to a client organisation."]
    }


@pytest.mark.parametrize(
    ("bad_id", "message"),
    [
        (True, "Not a valid integer."),
        ("3", "Not a valid integer."),
        (1.5, "Not a valid integer."),
        (0, "Organisation id must be a positive number."),
        (-1, "Organisation id must be a positive number."),
    ],
)
def test_organisation_id_must_be_a_positive_whole_number(
    db_session: Session,
    bad_id: Any,
    message: str,
    organiser_registration_payload: OrganiserPayload,
) -> None:
    assert _rejected_details(db_session, organiser_registration_payload(bad_id)) == {
        "organisation_id": [message]
    }


# --------------------------------------------------------------------------
# AC3 — two Event Organisers can belong to the same client organisation
# --------------------------------------------------------------------------


def test_two_organisers_can_belong_to_the_same_organisation(
    db_session: Session,
    organisation: ClientOrganisation,
    organiser_registration_payload: OrganiserPayload,
) -> None:
    first_payload = organiser_registration_payload(organisation.id)
    second_payload = {**first_payload, "email": "second.organiser@example.com"}

    first = register_user(first_payload, session=db_session)
    second = register_user(second_payload, session=db_session)

    assert first.id != second.id
    assert (first.organisation_id, second.organisation_id) == (organisation.id, organisation.id)
