"""Unit tests for SCRUM-25 — Update venue catalogue.

Services are exercised directly with a mocked DB session, same style as
Sprint 1's auth tests. Query-level filtering (e.g. ``is_active`` in SQL) is
trusted to the ORM and covered by the migration/CI `flask db check` step;
what's unit-tested here is the Python-level business logic.
"""

from __future__ import annotations

import pytest

from app.common.errors import NotFoundError, ValidationError
from app.modules.venue import services

pytestmark = pytest.mark.story_venue_catalogue


# --------------------------------------------------------------------------
# AC1 — create: editable fields persisted
# --------------------------------------------------------------------------


def test_create_venue_persists_all_editable_fields(mock_session) -> None:
    payload = {
        "name": "Grand Hall",
        "location": "Building B",
        "capacity": 250,
        "facilities": ["projector", "stage"],
        "accessibility_features": ["wheelchair_access"],
        "supported_layouts": ["theatre", "banquet"],
        "operating_hours_start": "08:00",
        "operating_hours_end": "20:00",
    }

    venue = services.create_venue(payload, session=mock_session)

    assert venue.name == "Grand Hall"
    assert venue.location == "Building B"
    assert venue.capacity == 250
    assert venue.facilities_list() == ["projector", "stage"]
    assert venue.accessibility_list() == ["wheelchair_access"]
    assert venue.layouts_list() == ["theatre", "banquet"]
    assert venue.operating_hours_start == "08:00"
    assert venue.operating_hours_end == "20:00"
    mock_session.add.assert_called_once_with(venue)
    mock_session.commit.assert_called_once()


# --------------------------------------------------------------------------
# AC2 — required fields cannot be blank, invalid values rejected
# --------------------------------------------------------------------------


@pytest.mark.parametrize("missing_field", ["name", "location", "capacity"])
def test_create_venue_missing_required_field_is_rejected(mock_session, missing_field: str) -> None:
    payload = {"name": "Hall", "location": "A", "capacity": 10}
    del payload[missing_field]

    with pytest.raises(ValidationError) as exc_info:
        services.create_venue(payload, session=mock_session)

    assert exc_info.value.status_code == 400
    assert missing_field in exc_info.value.details
    mock_session.add.assert_not_called()


@pytest.mark.parametrize("blank_field", ["name", "location"])
def test_create_venue_blank_required_field_is_rejected(mock_session, blank_field: str) -> None:
    payload = {"name": "Hall", "location": "A", "capacity": 10}
    payload[blank_field] = ""

    with pytest.raises(ValidationError):
        services.create_venue(payload, session=mock_session)


@pytest.mark.parametrize("capacity", [0, -5])
def test_create_venue_non_positive_capacity_is_rejected(mock_session, capacity: int) -> None:
    payload = {"name": "Hall", "location": "A", "capacity": capacity}

    with pytest.raises(ValidationError) as exc_info:
        services.create_venue(payload, session=mock_session)

    assert "capacity" in exc_info.value.details


# --------------------------------------------------------------------------
# AC2 (SCRUM-67 AC2) — buffer fields default when not set explicitly
# --------------------------------------------------------------------------


def test_create_venue_defaults_setup_and_turnaround_when_omitted(mock_session, app) -> None:
    payload = {"name": "Hall", "location": "A", "capacity": 10}

    venue = services.create_venue(payload, session=mock_session)

    assert venue.setup_minutes == app.config["DEFAULT_VENUE_SETUP_MINUTES"]
    assert venue.turnaround_minutes == app.config["DEFAULT_VENUE_TURNAROUND_MINUTES"]


def test_create_venue_keeps_explicit_buffer_values(mock_session) -> None:
    payload = {"name": "Hall", "location": "A", "capacity": 10, "setup_minutes": 15, "turnaround_minutes": 45}

    venue = services.create_venue(payload, session=mock_session)

    assert venue.setup_minutes == 15
    assert venue.turnaround_minutes == 45


@pytest.mark.parametrize("field", ["setup_minutes", "turnaround_minutes"])
def test_create_venue_negative_buffer_is_rejected(mock_session, field: str) -> None:
    payload = {"name": "Hall", "location": "A", "capacity": 10, field: -1}

    with pytest.raises(ValidationError) as exc_info:
        services.create_venue(payload, session=mock_session)

    assert field in exc_info.value.details


# --------------------------------------------------------------------------
# Update — only supplied fields change; same validation applies
# --------------------------------------------------------------------------


def test_update_venue_changes_only_supplied_fields(mock_session, make_venue) -> None:
    venue = make_venue(name="Old Name", capacity=100)
    mock_session.get.return_value = venue
    mock_session.scalars.return_value.all.return_value = []  # no confirmed bookings to re-check

    updated, warnings = services.update_venue(venue.id, {"capacity": 150}, session=mock_session)

    assert updated.capacity == 150
    assert updated.name == "Old Name"  # untouched
    assert warnings == []


def test_update_venue_rejects_invalid_capacity(mock_session, make_venue) -> None:
    venue = make_venue()
    mock_session.get.return_value = venue

    with pytest.raises(ValidationError):
        services.update_venue(venue.id, {"capacity": 0}, session=mock_session)

    mock_session.commit.assert_not_called()


def test_update_venue_unknown_id_is_not_found(mock_session) -> None:
    mock_session.get.return_value = None

    with pytest.raises(NotFoundError) as exc_info:
        services.update_venue(999, {"capacity": 50}, session=mock_session)

    assert exc_info.value.status_code == 404


def test_get_venue_unknown_id_is_not_found(mock_session) -> None:
    mock_session.get.return_value = None

    with pytest.raises(NotFoundError):
        services.get_venue(999, session=mock_session)


# --------------------------------------------------------------------------
# AC5/AC6 — deactivate / reactivate
# --------------------------------------------------------------------------


def test_deactivate_venue_flips_is_active_false(mock_session, make_venue) -> None:
    venue = make_venue(is_active=True)
    mock_session.get.return_value = venue

    result = services.deactivate_venue(venue.id, session=mock_session)

    assert result.is_active is False
    mock_session.commit.assert_called_once()


def test_reactivate_venue_flips_is_active_true(mock_session, make_venue) -> None:
    venue = make_venue(is_active=False)
    mock_session.get.return_value = venue

    result = services.reactivate_venue(venue.id, session=mock_session)

    assert result.is_active is True


def test_deactivate_unknown_venue_is_not_found(mock_session) -> None:
    mock_session.get.return_value = None

    with pytest.raises(NotFoundError):
        services.deactivate_venue(999, session=mock_session)
