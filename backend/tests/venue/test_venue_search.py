"""Unit tests for SCRUM-35 — Search and filter venues against event requirements.

``is_active`` / ``capacity >= min_capacity`` are filtered in SQL (trusted to
the ORM); everything else (location, facilities, layout, accessibility,
conflict-with-buffer) is Python-level filtering over the candidates the
mocked session returns, which is exactly what's unit-tested here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.common.errors import ValidationError
from app.modules.venue import services
from app.modules.venue.models import BookingStatus
from app.modules.venue.routes import _build_search_response

pytestmark = pytest.mark.story_venue_search


def _scalars(items: list) -> MagicMock:
    result = MagicMock()
    result.all.return_value = items
    return result


SEARCH_PAYLOAD = {
    "start_time": "2026-01-01T09:00:00+00:00",
    "end_time": "2026-01-01T11:00:00+00:00",
    "min_capacity": 10,
}


def _search(mock_session, venues: list, **overrides) -> list[dict]:
    """Run search_venues with `venues` as the SQL-filtered candidates and no
    existing bookings/blocks on any of them (unless overridden by the
    caller via a custom side_effect set beforehand)."""
    mock_session.scalars.side_effect = [_scalars(venues)] + [_scalars([]), _scalars([])] * len(venues)
    payload = {**SEARCH_PAYLOAD, **overrides}
    return services.search_venues(payload, session=mock_session)


# --------------------------------------------------------------------------
# AC1/AC2 — filters and result shape
# --------------------------------------------------------------------------


def test_search_requires_end_after_start(mock_session) -> None:
    with pytest.raises(ValidationError):
        services.search_venues(
            {"start_time": "2026-01-01T11:00:00+00:00", "end_time": "2026-01-01T09:00:00+00:00", "min_capacity": 5},
            session=mock_session,
        )


def test_search_result_shows_name_capacity_location_and_matches(mock_session, make_venue) -> None:
    venue = make_venue(name="Grand Hall", capacity=300, location="Building B", facilities="projector,wifi")
    results = _search(mock_session, [venue], required_facilities=["projector"])

    assert len(results) == 1
    assert results[0]["name"] == "Grand Hall"
    assert results[0]["capacity"] == 300
    assert results[0]["location"] == "Building B"
    assert results[0]["matched_requirements"]["facilities"] == ["projector"]


def test_search_filters_by_location_case_insensitive_substring(mock_session, make_venue) -> None:
    matching = make_venue(location="Building B - East Wing")
    non_matching = make_venue(location="Building C")

    results = _search(mock_session, [matching, non_matching], location="building b")

    assert len(results) == 1


def test_search_filters_by_required_layout(mock_session, make_venue) -> None:
    matching = make_venue(supported_layouts="theatre,classroom")
    non_matching = make_venue(supported_layouts="boardroom")

    results = _search(mock_session, [matching, non_matching], required_layout="theatre")

    assert len(results) == 1


def test_search_requires_all_required_facilities_present(mock_session, make_venue) -> None:
    partial = make_venue(facilities="projector")
    full = make_venue(facilities="projector,stage,wifi")

    results = _search(mock_session, [partial, full], required_facilities=["projector", "stage"])

    assert len(results) == 1


def test_search_requires_all_required_accessibility_features_present(mock_session, make_venue) -> None:
    partial = make_venue(accessibility_features="wheelchair_access")
    full = make_venue(accessibility_features="wheelchair_access,hearing_loop")

    results = _search(
        mock_session, [partial, full], required_accessibility=["wheelchair_access", "hearing_loop"]
    )

    assert len(results) == 1


# --------------------------------------------------------------------------
# AC1 — only venues free for the period are returned
# --------------------------------------------------------------------------


def test_search_excludes_venue_with_directly_overlapping_confirmed_booking(
    mock_session, make_venue, make_booking
) -> None:
    venue = make_venue(setup_minutes=0, turnaround_minutes=0)
    conflicting = make_booking(
        venue_id=venue.id,
        start_time=datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc),
        status=BookingStatus.CONFIRMED,
    )
    mock_session.scalars.side_effect = [_scalars([venue]), _scalars([conflicting]), _scalars([])]

    results = services.search_venues(SEARCH_PAYLOAD, session=mock_session)

    assert results == []


def test_search_excludes_venue_with_blocked_period(mock_session, make_venue, make_venue_block) -> None:
    venue = make_venue()
    block = make_venue_block(
        venue_id=venue.id,
        start_time=datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc),
    )
    mock_session.scalars.side_effect = [_scalars([venue]), _scalars([]), _scalars([block])]

    results = services.search_venues(SEARCH_PAYLOAD, session=mock_session)

    assert results == []


def test_search_includes_venue_free_for_the_whole_requested_period(
    mock_session, make_venue, make_booking
) -> None:
    venue = make_venue(setup_minutes=0, turnaround_minutes=0)
    earlier = make_booking(
        venue_id=venue.id,
        start_time=datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 7, 0, tzinfo=timezone.utc),
        status=BookingStatus.CONFIRMED,
    )
    mock_session.scalars.side_effect = [_scalars([venue]), _scalars([earlier]), _scalars([])]

    results = services.search_venues(SEARCH_PAYLOAD, session=mock_session)

    assert len(results) == 1


# --------------------------------------------------------------------------
# AC4 — a clear message is shown when nothing matches
# --------------------------------------------------------------------------


def test_build_search_response_includes_message_when_empty() -> None:
    body = _build_search_response([])

    assert body["results"] == []
    assert "message" in body and body["message"]


def test_build_search_response_has_no_message_when_results_present() -> None:
    body = _build_search_response([{"id": 1}])

    assert "message" not in body
