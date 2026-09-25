"""Unit tests for SCRUM-25 — Update venue catalogue.

Services run against ``db_session``, an in-memory SQLite database, so their
queries really execute: dropping the ``is_active`` filter or the ordering from
``list_venues`` fails a test here. Route permissions (AC4) are covered in
``test_venue_permissions.py``, opening hours in ``test_venue_opening_hours.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError, ValidationError
from app.modules.venue import services
from app.modules.venue.models import LIST_ITEM_MAX_LENGTH, LIST_MAX_ITEMS, LayoutType, Venue
from app.modules.venue.schemas import VenueSchema

pytestmark = pytest.mark.scrum_25

MakeVenue = Callable[..., Venue]

VALID_PAYLOAD: dict[str, Any] = {"name": "Hall", "location": "A", "capacity": 10}
FREE_TEXT_LIST_FIELDS = ["facilities", "accessibility_features"]


def _stored_venues(session: Session) -> list[Venue]:
    return list(session.scalars(select(Venue)))


# --------------------------------------------------------------------------
# AC1 — create: every editable field is saved and shown
# --------------------------------------------------------------------------


def test_create_venue_saves_every_editable_field(
    db_session: Session, reload_venue: Callable[[int], Venue]
) -> None:
    payload = {
        "name": "Grand Hall",
        "location": "Building B",
        "capacity": 250,
        "facilities": ["projector", "stage"],
        "accessibility_features": ["wheelchair_access"],
        "supported_layouts": ["theatre", "banquet"],
        "opening_hours": [
            {
                "open": {"day": "monday", "time": "08:00"},
                "close": {"day": "monday", "time": "20:00"},
            }
        ],
    }

    created = services.create_venue(payload, session=db_session)

    assert VenueSchema().dump(reload_venue(created.id)) == {
        "id": created.id,
        "name": "Grand Hall",
        "location": "Building B",
        "capacity": 250,
        "facilities": ["projector", "stage"],
        "accessibility_features": ["wheelchair_access"],
        "supported_layouts": ["theatre", "banquet"],
        "opening_hours": payload["opening_hours"],
        "is_active": True,
    }


@pytest.mark.parametrize("field", FREE_TEXT_LIST_FIELDS)
def test_list_items_are_saved_trimmed_and_lower_cased(
    db_session: Session, field: str, reload_venue: Callable[[int], Venue]
) -> None:
    """One matching rule for search: items are compared as stored, lower case."""
    payload = {**VALID_PAYLOAD, field: [" Projector ", "PA System"]}

    created = services.create_venue(payload, session=db_session)

    assert VenueSchema().dump(reload_venue(created.id))[field] == ["projector", "pa system"]


# --------------------------------------------------------------------------
# AC2 — required fields can't be blank; invalid values are rejected
# --------------------------------------------------------------------------


@pytest.mark.parametrize("missing_field", ["name", "location", "capacity"])
def test_missing_required_field_is_rejected(db_session: Session, missing_field: str) -> None:
    payload = dict(VALID_PAYLOAD)
    del payload[missing_field]

    with pytest.raises(ValidationError) as exc_info:
        services.create_venue(payload, session=db_session)

    assert exc_info.value.status_code == 400
    assert missing_field in exc_info.value.details
    assert _stored_venues(db_session) == []


@pytest.mark.parametrize("blank_value", ["", "   "], ids=["empty", "whitespace"])
@pytest.mark.parametrize("blank_field", ["name", "location"])
def test_blank_required_field_is_rejected(
    db_session: Session, blank_field: str, blank_value: str
) -> None:
    payload = {**VALID_PAYLOAD, blank_field: blank_value}

    with pytest.raises(ValidationError) as exc_info:
        services.create_venue(payload, session=db_session)

    assert blank_field in exc_info.value.details
    assert _stored_venues(db_session) == []


def test_name_and_location_are_trimmed(
    db_session: Session, reload_venue: Callable[[int], Venue]
) -> None:
    payload = {"name": "  Grand Hall ", "location": " Building B  ", "capacity": 10}

    created = services.create_venue(payload, session=db_session)

    stored = reload_venue(created.id)
    assert (stored.name, stored.location) == ("Grand Hall", "Building B")


@pytest.mark.parametrize("capacity", [0, -5])
def test_non_positive_capacity_is_rejected(db_session: Session, capacity: int) -> None:
    with pytest.raises(ValidationError) as exc_info:
        services.create_venue({**VALID_PAYLOAD, "capacity": capacity}, session=db_session)

    assert exc_info.value.details == {"capacity": ["Capacity must be a positive number."]}


@pytest.mark.parametrize("field", FREE_TEXT_LIST_FIELDS)
@pytest.mark.parametrize("bad_item", ["projector,screen", "", "   "])
def test_list_items_that_would_not_round_trip_are_rejected(
    db_session: Session, field: str, bad_item: str
) -> None:
    """A separator inside an item would silently split into two items on read."""
    payload = {**VALID_PAYLOAD, field: ["wifi", bad_item]}

    with pytest.raises(ValidationError) as exc_info:
        services.create_venue(payload, session=db_session)

    assert field in exc_info.value.details
    assert _stored_venues(db_session) == []


# --------------------------------------------------------------------------
# AC2 — list sizes: user input can never overflow its column (a 500 on Postgres)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field", FREE_TEXT_LIST_FIELDS)
def test_an_item_over_the_length_limit_is_rejected(db_session: Session, field: str) -> None:
    payload = {**VALID_PAYLOAD, field: ["x" * (LIST_ITEM_MAX_LENGTH + 1)]}

    with pytest.raises(ValidationError) as exc_info:
        services.create_venue(payload, session=db_session)

    assert field in exc_info.value.details
    assert _stored_venues(db_session) == []


@pytest.mark.parametrize("field", FREE_TEXT_LIST_FIELDS)
def test_more_items_than_the_limit_is_rejected(db_session: Session, field: str) -> None:
    payload = {**VALID_PAYLOAD, field: [f"item {n}" for n in range(LIST_MAX_ITEMS + 1)]}

    with pytest.raises(ValidationError) as exc_info:
        services.create_venue(payload, session=db_session)

    assert field in exc_info.value.details
    assert _stored_venues(db_session) == []


@pytest.mark.parametrize("field", FREE_TEXT_LIST_FIELDS)
def test_the_largest_accepted_list_fits_its_column(
    db_session: Session, field: str, reload_venue: Callable[[int], Venue]
) -> None:
    items = [f"{n:02d}".ljust(LIST_ITEM_MAX_LENGTH, "x") for n in range(LIST_MAX_ITEMS)]

    created = services.create_venue({**VALID_PAYLOAD, field: items}, session=db_session)

    column_length = Venue.__table__.c[field].type.length
    assert len(getattr(reload_venue(created.id), field)) <= column_length


def test_more_layouts_than_exist_is_rejected(db_session: Session) -> None:
    payload = {**VALID_PAYLOAD, "supported_layouts": ["other"] * (len(LayoutType) + 1)}

    with pytest.raises(ValidationError) as exc_info:
        services.create_venue(payload, session=db_session)

    assert "supported_layouts" in exc_info.value.details


# --------------------------------------------------------------------------
# AC3 / AC5 — the listing shows active venues only, by name
# --------------------------------------------------------------------------


def test_list_shows_only_active_venues_ordered_by_name(
    db_session: Session, make_venue: MakeVenue, save: Callable[..., None]
) -> None:
    save(
        make_venue(name="Cedar Room"),
        make_venue(name="Annex", is_active=False),
        make_venue(name="Birch Hall"),
    )

    listed = services.list_venues(session=db_session)

    assert [venue.name for venue in listed] == ["Birch Hall", "Cedar Room"]


def test_a_deactivated_venue_can_still_be_fetched_by_id(
    db_session: Session, make_venue: MakeVenue, save: Callable[..., None]
) -> None:
    """AC5: it stays attached to bookings already made, so it must stay reachable."""
    venue = make_venue(is_active=False)
    save(venue)

    assert services.get_venue(venue.id, session=db_session) is venue


def test_get_unknown_venue_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        services.get_venue(999, session=db_session)

    assert exc_info.value.status_code == 404


# --------------------------------------------------------------------------
# Update — only the fields sent change; the same validation applies
# --------------------------------------------------------------------------


def test_update_changes_only_the_fields_sent(
    db_session: Session,
    make_venue: MakeVenue,
    save: Callable[..., None],
    reload_venue: Callable[[int], Venue],
) -> None:
    venue = make_venue(name="Old Name", capacity=100)
    save(venue)

    services.update_venue(venue.id, {"capacity": 150}, session=db_session)

    stored = reload_venue(venue.id)
    assert (stored.name, stored.capacity) == ("Old Name", 150)


def test_update_rejects_invalid_capacity_and_saves_nothing(
    db_session: Session,
    make_venue: MakeVenue,
    save: Callable[..., None],
    reload_venue: Callable[[int], Venue],
) -> None:
    venue = make_venue(capacity=100)
    save(venue)

    with pytest.raises(ValidationError):
        services.update_venue(venue.id, {"capacity": 0}, session=db_session)

    assert reload_venue(venue.id).capacity == 100


@pytest.mark.parametrize("blank_value", ["", "   "], ids=["empty", "whitespace"])
@pytest.mark.parametrize("blank_field", ["name", "location"])
def test_update_rejects_blank_required_field(
    db_session: Session,
    make_venue: MakeVenue,
    blank_field: str,
    blank_value: str,
    save: Callable[..., None],
) -> None:
    venue = make_venue()
    save(venue)

    with pytest.raises(ValidationError) as exc_info:
        services.update_venue(venue.id, {blank_field: blank_value}, session=db_session)

    assert blank_field in exc_info.value.details


def test_update_trims_name_and_location(
    db_session: Session,
    make_venue: MakeVenue,
    save: Callable[..., None],
    reload_venue: Callable[[int], Venue],
) -> None:
    venue = make_venue()
    save(venue)

    services.update_venue(
        venue.id, {"name": " New Name ", "location": "  Annex "}, session=db_session
    )

    stored = reload_venue(venue.id)
    assert (stored.name, stored.location) == ("New Name", "Annex")


def test_update_normalises_list_items(
    db_session: Session,
    make_venue: MakeVenue,
    save: Callable[..., None],
    reload_venue: Callable[[int], Venue],
) -> None:
    venue = make_venue()
    save(venue)

    services.update_venue(venue.id, {"facilities": [" Stage ", "WiFi"]}, session=db_session)

    assert reload_venue(venue.id).facilities_list() == ["stage", "wifi"]


def test_update_unknown_venue_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        services.update_venue(999, {"capacity": 50}, session=db_session)


# --------------------------------------------------------------------------
# AC5 / AC6 — deactivate and reactivate
# --------------------------------------------------------------------------


def test_deactivate_saves_the_venue_as_inactive(
    db_session: Session,
    make_venue: MakeVenue,
    save: Callable[..., None],
    reload_venue: Callable[[int], Venue],
) -> None:
    venue = make_venue(is_active=True)
    save(venue)

    services.deactivate_venue(venue.id, session=db_session)

    assert reload_venue(venue.id).is_active is False


def test_reactivate_saves_the_venue_as_active(
    db_session: Session,
    make_venue: MakeVenue,
    save: Callable[..., None],
    reload_venue: Callable[[int], Venue],
) -> None:
    venue = make_venue(is_active=False)
    save(venue)

    services.reactivate_venue(venue.id, session=db_session)

    assert reload_venue(venue.id).is_active is True


@pytest.mark.parametrize("action", [services.deactivate_venue, services.reactivate_venue])
def test_deactivating_or_reactivating_an_unknown_venue_is_not_found(
    db_session: Session, action: Callable[..., Venue]
) -> None:
    with pytest.raises(NotFoundError):
        action(999, session=db_session)
