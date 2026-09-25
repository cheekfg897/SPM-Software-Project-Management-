"""Unit tests for SCRUM-27 — Maintain the equipment catalogue.

Covers AC1 (create and edit an equipment type), AC2 (view every type with its total
quantity) and ADR-0014 (one uniquely named record, at one venue or one store).
Services run against ``db_session``, an in-memory SQLite database, so the ordering,
the unique name and the check constraints really run. Route permissions (AC3) are
covered in ``test_equipment_permissions.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.equipment import services
from app.modules.equipment.models import EquipmentType
from app.modules.equipment.schemas import (
    BOTH_LOCATIONS_MESSAGE,
    NO_LOCATION_MESSAGE,
    EquipmentTypeSchema,
)
from app.modules.venue.models import Venue

pytestmark = pytest.mark.scrum_27

MakeEquipmentType = Callable[..., EquipmentType]
ReloadEquipmentType = Callable[[int], EquipmentType]
Save = Callable[..., None]

VALID_PAYLOAD: dict[str, Any] = {
    "name": "Projector",
    "total_quantity": 10,
    "store_name": "Central AV store",
}
#: No venue or equipment type in these tests has this id.
UNKNOWN_ID = 999
TOO_LONG = "x" * 201
AT_MAX_LENGTH = "x" * 200


def _stored(session: Session) -> list[EquipmentType]:
    return list(session.scalars(select(EquipmentType)))


def _create_rejected(session: Session, payload: dict[str, Any]) -> ValidationError:
    """Create with an invalid payload; check it's a 400 that stores nothing."""
    with pytest.raises(ValidationError) as exc_info:
        services.create_equipment_type(payload, session=session)

    assert exc_info.value.status_code == 400
    assert _stored(session) == []
    return exc_info.value


def _update_rejected(
    session: Session, equipment_type: EquipmentType, payload: dict[str, Any]
) -> ValidationError:
    """Update with an invalid payload; check it's a 400 that changes nothing."""
    before = EquipmentTypeSchema().dump(equipment_type)

    with pytest.raises(ValidationError) as exc_info:
        services.update_equipment_type(equipment_type.id, payload, session=session)

    assert exc_info.value.status_code == 400
    session.expire_all()
    assert EquipmentTypeSchema().dump(session.get(EquipmentType, equipment_type.id)) == before
    return exc_info.value


# --------------------------------------------------------------------------
# AC1 — create an equipment type
# --------------------------------------------------------------------------


def test_create_saves_every_field_and_shows_it(
    db_session: Session, venue: Venue, reload_equipment_type: ReloadEquipmentType
) -> None:
    payload = {
        "name": "Projector",
        "description": "4K, with HDMI and USB-C",
        "total_quantity": 12,
        "venue_id": venue.id,
    }

    created = services.create_equipment_type(payload, session=db_session)

    assert EquipmentTypeSchema().dump(reload_equipment_type(created.id)) == {
        "id": created.id,
        "name": "Projector",
        "description": "4K, with HDMI and USB-C",
        "total_quantity": 12,
        "venue_id": venue.id,
        "store_name": None,
    }


def test_create_at_a_store_saves_the_store_and_no_venue(
    db_session: Session, reload_equipment_type: ReloadEquipmentType
) -> None:
    created = services.create_equipment_type(VALID_PAYLOAD, session=db_session)

    stored = reload_equipment_type(created.id)
    assert (stored.venue_id, stored.store_name) == (None, "Central AV store")


@pytest.mark.parametrize("missing_field", ["name", "total_quantity"])
def test_missing_required_field_is_rejected(db_session: Session, missing_field: str) -> None:
    payload = dict(VALID_PAYLOAD)
    del payload[missing_field]

    error = _create_rejected(db_session, payload)

    assert missing_field in error.details


@pytest.mark.parametrize("blank_value", ["", "   "], ids=["empty", "whitespace"])
@pytest.mark.parametrize("blank_field", ["name", "store_name"])
def test_blank_name_or_store_is_rejected(
    db_session: Session, blank_field: str, blank_value: str
) -> None:
    error = _create_rejected(db_session, {**VALID_PAYLOAD, blank_field: blank_value})

    assert error.details == {blank_field: ["Must not be blank."]}


def test_name_description_and_store_are_trimmed(
    db_session: Session, reload_equipment_type: ReloadEquipmentType
) -> None:
    payload = {
        "name": "  Projector ",
        "description": "  4K  ",
        "total_quantity": 1,
        "store_name": " Central AV store  ",
    }

    created = services.create_equipment_type(payload, session=db_session)

    stored = reload_equipment_type(created.id)
    assert (stored.name, stored.description, stored.store_name) == (
        "Projector",
        "4K",
        "Central AV store",
    )


@pytest.mark.parametrize("description", ["", "   "], ids=["empty", "whitespace"])
def test_blank_description_is_saved_as_null(
    db_session: Session, description: str, reload_equipment_type: ReloadEquipmentType
) -> None:
    payload = {**VALID_PAYLOAD, "description": description}

    created = services.create_equipment_type(payload, session=db_session)

    assert reload_equipment_type(created.id).description is None


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("name", "Name must be at most 200 characters."),
        ("store_name", "Store name must be at most 200 characters."),
    ],
)
def test_over_long_name_or_store_is_rejected(db_session: Session, field: str, message: str) -> None:
    error = _create_rejected(db_session, {**VALID_PAYLOAD, field: TOO_LONG})

    assert error.details == {field: [message]}


@pytest.mark.parametrize("field", ["name", "store_name"])
def test_name_or_store_of_the_maximum_length_is_accepted(
    db_session: Session, field: str, reload_equipment_type: ReloadEquipmentType
) -> None:
    created = services.create_equipment_type(
        {**VALID_PAYLOAD, field: AT_MAX_LENGTH}, session=db_session
    )

    assert getattr(reload_equipment_type(created.id), field) == AT_MAX_LENGTH


def test_negative_total_quantity_is_rejected(db_session: Session) -> None:
    error = _create_rejected(db_session, {**VALID_PAYLOAD, "total_quantity": -1})

    assert error.details == {"total_quantity": ["Total quantity cannot be negative."]}


def test_zero_total_quantity_is_accepted(
    db_session: Session, reload_equipment_type: ReloadEquipmentType
) -> None:
    """A retired type keeps its record, with nothing held (ADR-0014)."""
    created = services.create_equipment_type(
        {**VALID_PAYLOAD, "total_quantity": 0}, session=db_session
    )

    assert reload_equipment_type(created.id).total_quantity == 0


@pytest.mark.parametrize("quantity", ["5", 5.5, True], ids=["string", "fraction", "boolean"])
def test_total_quantity_must_be_a_whole_number(db_session: Session, quantity: Any) -> None:
    error = _create_rejected(db_session, {**VALID_PAYLOAD, "total_quantity": quantity})

    assert list(error.details) == ["total_quantity"]


@pytest.mark.parametrize(
    ("location", "message"),
    [
        ({}, NO_LOCATION_MESSAGE),
        ({"venue_id": None, "store_name": None}, NO_LOCATION_MESSAGE),
        ({"venue_id": 1, "store_name": "Central AV store"}, BOTH_LOCATIONS_MESSAGE),
    ],
    ids=["neither-sent", "both-null", "both-set"],
)
def test_exactly_one_location_is_required(
    db_session: Session, location: dict[str, Any], message: str
) -> None:
    payload = {"name": "Projector", "total_quantity": 10, **location}

    error = _create_rejected(db_session, payload)

    assert error.details == {"venue_id": [message]}


def test_unknown_venue_is_rejected(db_session: Session) -> None:
    payload = {"name": "Projector", "total_quantity": 10, "venue_id": UNKNOWN_ID}

    error = _create_rejected(db_session, payload)

    assert error.details == {"venue_id": ["Venue not found."]}


@pytest.mark.parametrize("venue_id", [0, -1])
def test_venue_id_must_be_positive(db_session: Session, venue_id: int) -> None:
    payload = {"name": "Projector", "total_quantity": 10, "venue_id": venue_id}

    error = _create_rejected(db_session, payload)

    assert error.details == {"venue_id": ["venue_id must be a positive number."]}


def test_a_deactivated_venue_can_still_hold_equipment(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Save,
    reload_equipment_type: ReloadEquipmentType,
) -> None:
    closed_venue = make_venue(is_active=False)
    save(closed_venue)
    payload = {"name": "Projector", "total_quantity": 10, "venue_id": closed_venue.id}

    created = services.create_equipment_type(payload, session=db_session)

    assert reload_equipment_type(created.id).venue_id == closed_venue.id


def test_duplicate_name_is_a_conflict(db_session: Session, equipment_type: EquipmentType) -> None:
    with pytest.raises(ConflictError) as exc_info:
        services.create_equipment_type(VALID_PAYLOAD, session=db_session)

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == "An equipment type with this name already exists."
    # Querying again only works if the failed commit was rolled back.
    assert [stored.id for stored in _stored(db_session)] == [equipment_type.id]


# --------------------------------------------------------------------------
# AC2 — view every equipment type with its total quantity
# --------------------------------------------------------------------------


def test_list_shows_every_type_with_its_total_quantity_by_name(
    db_session: Session, make_equipment_type: MakeEquipmentType, save: Save
) -> None:
    save(
        make_equipment_type(name="Speaker", total_quantity=4),
        make_equipment_type(name="Projector", total_quantity=10),
        make_equipment_type(name="Microphone", total_quantity=20),
    )

    listed = services.list_equipment_types(session=db_session)

    assert [(item.name, item.total_quantity) for item in listed] == [
        ("Microphone", 20),
        ("Projector", 10),
        ("Speaker", 4),
    ]


def test_get_returns_the_equipment_type_asked_for(
    db_session: Session, make_equipment_type: MakeEquipmentType, save: Save
) -> None:
    microphone = make_equipment_type(name="Microphone")
    save(make_equipment_type(name="Projector"), microphone)

    fetched = services.get_equipment_type(microphone.id, session=db_session)

    assert (fetched.id, fetched.name) == (microphone.id, "Microphone")


def test_get_unknown_equipment_type_is_404(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        services.get_equipment_type(UNKNOWN_ID, session=db_session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Equipment type not found."


# --------------------------------------------------------------------------
# AC1 — edit an equipment type
# --------------------------------------------------------------------------


def test_update_changes_only_the_fields_sent(
    db_session: Session,
    equipment_type: EquipmentType,
    reload_equipment_type: ReloadEquipmentType,
) -> None:
    services.update_equipment_type(
        equipment_type.id, {"total_quantity": 15, "name": " Laser projector "}, session=db_session
    )

    assert EquipmentTypeSchema().dump(reload_equipment_type(equipment_type.id)) == {
        "id": equipment_type.id,
        "name": "Laser projector",
        "description": None,
        "total_quantity": 15,
        "venue_id": None,
        "store_name": "Central AV store",
    }


@pytest.mark.parametrize(
    "payload",
    [{"total_quantity": -1}, {"name": ""}, {"name": None}, {"total_quantity": None}],
    ids=["negative-quantity", "blank-name", "null-name", "null-quantity"],
)
def test_update_rejects_invalid_values_and_saves_nothing(
    db_session: Session, equipment_type: EquipmentType, payload: dict[str, Any]
) -> None:
    error = _update_rejected(db_session, equipment_type, payload)

    assert list(error.details) == list(payload)


def test_update_moves_equipment_from_a_store_to_a_venue(
    db_session: Session,
    equipment_type: EquipmentType,
    venue: Venue,
    reload_equipment_type: ReloadEquipmentType,
) -> None:
    services.update_equipment_type(equipment_type.id, {"venue_id": venue.id}, session=db_session)

    stored = reload_equipment_type(equipment_type.id)
    assert (stored.venue_id, stored.store_name) == (venue.id, None)


def test_update_moves_equipment_from_a_venue_to_a_store(
    db_session: Session,
    make_equipment_type: MakeEquipmentType,
    save: Save,
    venue: Venue,
    reload_equipment_type: ReloadEquipmentType,
) -> None:
    at_venue = make_equipment_type(venue_id=venue.id, store_name=None)
    save(at_venue)

    services.update_equipment_type(
        at_venue.id, {"store_name": " Basement store "}, session=db_session
    )

    stored = reload_equipment_type(at_venue.id)
    assert (stored.venue_id, stored.store_name) == (None, "Basement store")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"store_name": None}, NO_LOCATION_MESSAGE),
        ({"venue_id": None, "store_name": None}, NO_LOCATION_MESSAGE),
        ({"venue_id": 1, "store_name": "Basement store"}, BOTH_LOCATIONS_MESSAGE),
    ],
    ids=["clear-store", "clear-both", "set-both"],
)
def test_update_keeps_exactly_one_location(
    db_session: Session, equipment_type: EquipmentType, payload: dict[str, Any], message: str
) -> None:
    error = _update_rejected(db_session, equipment_type, payload)

    assert error.details == {"venue_id": [message]}


def test_update_to_an_unknown_venue_is_rejected(
    db_session: Session, equipment_type: EquipmentType
) -> None:
    error = _update_rejected(db_session, equipment_type, {"venue_id": UNKNOWN_ID})

    assert error.details == {"venue_id": ["Venue not found."]}


def test_renaming_to_an_existing_name_is_a_conflict(
    db_session: Session,
    make_equipment_type: MakeEquipmentType,
    save: Save,
    reload_equipment_type: ReloadEquipmentType,
) -> None:
    microphone = make_equipment_type(name="Microphone")
    save(make_equipment_type(name="Projector"), microphone)

    with pytest.raises(ConflictError) as exc_info:
        services.update_equipment_type(microphone.id, {"name": "Projector"}, session=db_session)

    assert exc_info.value.status_code == 409
    assert reload_equipment_type(microphone.id).name == "Microphone"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [({"description": None}, None), ({"total_quantity": 3}, "4K")],
    ids=["null-clears-it", "not-sent-leaves-it"],
)
def test_update_clears_the_description_only_when_it_is_sent_as_null(
    db_session: Session,
    make_equipment_type: MakeEquipmentType,
    save: Save,
    reload_equipment_type: ReloadEquipmentType,
    payload: dict[str, Any],
    expected: str | None,
) -> None:
    described = make_equipment_type(description="4K")
    save(described)

    services.update_equipment_type(described.id, payload, session=db_session)

    assert reload_equipment_type(described.id).description == expected


def test_update_unknown_equipment_type_is_404(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        services.update_equipment_type(UNKNOWN_ID, {"total_quantity": 1}, session=db_session)

    assert exc_info.value.status_code == 404


# --------------------------------------------------------------------------
# ADR-0014 — the database holds the same rules as the schema
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [{"total_quantity": -1}, {"store_name": None}, {"name": "Existing"}],
    ids=["negative-quantity", "no-location", "duplicate-name"],
)
def test_database_rejects_a_row_that_breaks_a_rule(
    make_equipment_type: MakeEquipmentType, save: Save, fields: dict[str, Any]
) -> None:
    save(make_equipment_type(name="Existing"))

    with pytest.raises(IntegrityError):
        save(make_equipment_type(**fields))


def test_database_rejects_a_row_at_a_venue_and_a_store(
    make_equipment_type: MakeEquipmentType, save: Save, venue: Venue
) -> None:
    with pytest.raises(IntegrityError):
        save(make_equipment_type(venue_id=venue.id, store_name="Central AV store"))
