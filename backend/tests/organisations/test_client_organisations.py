"""Unit tests for SCRUM-66 AC1 — a client organisation records name and contact details.

Services run against ``db_session``, an in-memory SQLite database, so the unique name
and the ordering really execute. Who may call the routes (AC5) is covered in
``test_client_organisations_permissions.py``. Decisions are in ADR-0013.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.organisations import services
from app.modules.organisations.models import ClientOrganisation
from app.modules.organisations.schemas import ClientOrganisationSchema

pytestmark = pytest.mark.scrum_66

REQUIRED_FIELDS = ["name", "contact_name", "contact_email"]


def _stored(session: Session) -> list[ClientOrganisation]:
    return list(session.scalars(select(ClientOrganisation)))


def _rejected_details(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Create with ``payload``; expect a 400 and nothing saved. Returns the details."""
    with pytest.raises(ValidationError) as exc_info:
        services.create_organisation(payload, session=session)

    assert exc_info.value.status_code == 400
    assert _stored(session) == []
    return exc_info.value.details or {}


def _reload(session: Session, organisation_id: int) -> ClientOrganisation:
    session.expire_all()
    organisation = session.get(ClientOrganisation, organisation_id)
    assert organisation is not None
    return organisation


# --------------------------------------------------------------------------
# AC1 — name and contact details are recorded
# --------------------------------------------------------------------------


def test_create_saves_name_and_contact_details(
    db_session: Session, valid_organisation_payload: dict[str, Any]
) -> None:
    payload = {**valid_organisation_payload, "contact_phone": "+65 6123 4567"}

    created = services.create_organisation(payload, session=db_session)

    dumped = ClientOrganisationSchema().dump(_reload(db_session, created.id))
    assert dumped.pop("created_at") is not None
    assert dumped == {"id": created.id, **payload}


def test_name_and_contact_fields_are_trimmed(
    db_session: Session, valid_organisation_payload: dict[str, Any]
) -> None:
    payload = {
        **valid_organisation_payload,
        "name": "  Acme Events ",
        "contact_name": " Alice Tan  ",
        "contact_phone": " +65 6123 4567 ",
    }

    created = services.create_organisation(payload, session=db_session)

    stored = _reload(db_session, created.id)
    assert (stored.name, stored.contact_name, stored.contact_phone) == (
        "Acme Events",
        "Alice Tan",
        "+65 6123 4567",
    )


@pytest.mark.parametrize("missing_field", REQUIRED_FIELDS)
def test_missing_required_field_is_rejected(
    db_session: Session, missing_field: str, valid_organisation_payload: dict[str, Any]
) -> None:
    payload = dict(valid_organisation_payload)
    del payload[missing_field]

    assert missing_field in _rejected_details(db_session, payload)


@pytest.mark.parametrize("blank_value", ["", "   "], ids=["empty", "whitespace"])
@pytest.mark.parametrize("blank_field", ["name", "contact_name"])
def test_blank_required_field_is_rejected(
    db_session: Session,
    blank_field: str,
    blank_value: str,
    valid_organisation_payload: dict[str, Any],
) -> None:
    payload = {**valid_organisation_payload, blank_field: blank_value}

    assert blank_field in _rejected_details(db_session, payload)


@pytest.mark.parametrize("bad_email", ["not-an-email", "", "   "])
def test_invalid_contact_email_is_rejected(
    db_session: Session, bad_email: str, valid_organisation_payload: dict[str, Any]
) -> None:
    payload = {**valid_organisation_payload, "contact_email": bad_email}

    assert "contact_email" in _rejected_details(db_session, payload)


@pytest.mark.parametrize("phone", [None, "", "   "], ids=["null", "empty", "whitespace"])
def test_blank_contact_phone_is_stored_as_null(
    db_session: Session, phone: str | None, valid_organisation_payload: dict[str, Any]
) -> None:
    created = services.create_organisation(
        {**valid_organisation_payload, "contact_phone": phone}, session=db_session
    )

    assert _reload(db_session, created.id).contact_phone is None


def test_contact_phone_can_be_left_out(
    db_session: Session, valid_organisation_payload: dict[str, Any]
) -> None:
    created = services.create_organisation(valid_organisation_payload, session=db_session)

    assert _reload(db_session, created.id).contact_phone is None


@pytest.mark.parametrize(
    "phone",
    [
        "61234567",
        "6123-4567",
        "+65 6123 4567",
        "+1 (415) 555-0100",
        "1234567",
        "7890123",
    ],
)
def test_contact_phone_in_a_usual_format_is_accepted(
    db_session: Session, phone: str, valid_organisation_payload: dict[str, Any]
) -> None:
    created = services.create_organisation(
        {**valid_organisation_payload, "contact_phone": phone}, session=db_session
    )

    assert _reload(db_session, created.id).contact_phone == phone


@pytest.mark.parametrize(
    "bad_phone",
    [
        "abc",
        "!!!",
        "call me maybe",
        "6123 4567 ext 2",
        "65+6123 4567",
        "++65 6123 4567",
        "123456",
        "\u0666\u0661\u0662\u0663\u0664\u0665\u0666\u0667",
    ],
    ids=[
        "letters",
        "symbols",
        "words",
        "extension",
        "plus-not-leading",
        "two-pluses",
        "six-digits",
        "non-ascii-digits",
    ],
)
def test_contact_phone_that_is_not_a_phone_number_is_rejected(
    db_session: Session, bad_phone: str, valid_organisation_payload: dict[str, Any]
) -> None:
    payload = {**valid_organisation_payload, "contact_phone": bad_phone}

    assert _rejected_details(db_session, payload) == {
        "contact_phone": [
            "Contact phone must have at least 7 digits and use only spaces, hyphens, "
            "brackets and a leading +."
        ]
    }


@pytest.mark.parametrize(
    ("field", "max_length", "message"),
    [
        ("name", 120, "Name must be at most 120 characters."),
        ("contact_name", 120, "Contact name must be at most 120 characters."),
        ("contact_phone", 30, "Contact phone must be at most 30 characters."),
    ],
)
def test_over_length_field_is_rejected(
    db_session: Session,
    field: str,
    max_length: int,
    message: str,
    valid_organisation_payload: dict[str, Any],
) -> None:
    payload = {**valid_organisation_payload, field: "1" * (max_length + 1)}

    assert _rejected_details(db_session, payload) == {field: [message]}


def test_over_length_contact_email_is_rejected(
    db_session: Session, valid_organisation_payload: dict[str, Any]
) -> None:
    """The column holds 255 characters; a longer address would be a 500 on Postgres."""
    domain = ".".join(["b" * 60] * 3) + ".example"  # valid labels, 190 characters
    payload = {**valid_organisation_payload, "contact_email": "a" * 70 + "@" + domain}  # 261

    assert _rejected_details(db_session, payload) == {
        "contact_email": ["Contact email must be at most 255 characters."]
    }


@pytest.mark.parametrize(
    ("field", "max_length"), [("name", 120), ("contact_name", 120), ("contact_phone", 30)]
)
def test_field_at_its_length_limit_is_accepted(
    db_session: Session, field: str, max_length: int, valid_organisation_payload: dict[str, Any]
) -> None:
    at_limit = "1" * max_length
    created = services.create_organisation(
        {**valid_organisation_payload, field: at_limit}, session=db_session
    )

    assert getattr(_reload(db_session, created.id), field) == at_limit


def test_unknown_field_is_rejected(
    db_session: Session, valid_organisation_payload: dict[str, Any]
) -> None:
    payload = {**valid_organisation_payload, "id": 5}

    assert "id" in _rejected_details(db_session, payload)


# --------------------------------------------------------------------------
# ADR-0013 — names are unique
# --------------------------------------------------------------------------


def test_duplicate_name_is_a_conflict(
    db_session: Session, valid_organisation_payload: dict[str, Any]
) -> None:
    services.create_organisation(valid_organisation_payload, session=db_session)

    with pytest.raises(ConflictError) as exc_info:
        services.create_organisation(
            {**valid_organisation_payload, "contact_name": "Bob Lim"}, session=db_session
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "conflict"
    assert exc_info.value.message == "A client organisation with this name already exists."
    assert [organisation.contact_name for organisation in _stored(db_session)] == ["Alice Tan"]


def test_duplicate_name_is_checked_after_trimming(
    db_session: Session, valid_organisation_payload: dict[str, Any]
) -> None:
    services.create_organisation(valid_organisation_payload, session=db_session)

    with pytest.raises(ConflictError):
        services.create_organisation(
            {**valid_organisation_payload, "name": " Acme Events "}, session=db_session
        )


def test_duplicate_name_is_refused_before_saving(
    mock_session: MagicMock,
    make_organisation: Callable[..., ClientOrganisation],
    valid_organisation_payload: dict[str, Any],
) -> None:
    mock_session.scalar.return_value = make_organisation()

    with pytest.raises(ConflictError):
        services.create_organisation(valid_organisation_payload, session=mock_session)

    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()


def test_race_on_unique_name_is_translated_to_conflict(
    mock_session: MagicMock, valid_organisation_payload: dict[str, Any]
) -> None:
    """The name check passes, but another request saves the same name before commit."""
    mock_session.commit.side_effect = IntegrityError("INSERT ...", {}, Exception("duplicate"))

    with pytest.raises(ConflictError) as exc_info:
        services.create_organisation(valid_organisation_payload, session=mock_session)

    assert exc_info.value.status_code == 409
    mock_session.rollback.assert_called_once()


# --------------------------------------------------------------------------
# Listing and fetching
# --------------------------------------------------------------------------


def test_list_returns_organisations_by_name(
    db_session: Session, valid_organisation_payload: dict[str, Any]
) -> None:
    for name in ["Cedar Partners", "Acme Events", "Birch Holdings"]:
        services.create_organisation(
            {**valid_organisation_payload, "name": name}, session=db_session
        )

    listed = services.list_organisations(session=db_session)

    assert [organisation.name for organisation in listed] == [
        "Acme Events",
        "Birch Holdings",
        "Cedar Partners",
    ]


def test_get_returns_the_organisation(
    db_session: Session, valid_organisation_payload: dict[str, Any]
) -> None:
    created = services.create_organisation(valid_organisation_payload, session=db_session)

    fetched = services.get_organisation(created.id, session=db_session)

    assert (fetched.id, fetched.name) == (created.id, "Acme Events")


def test_get_unknown_organisation_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        services.get_organisation(999, session=db_session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Client organisation not found."
