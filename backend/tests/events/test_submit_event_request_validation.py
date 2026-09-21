"""Unit tests for SCRUM-19 "Submit an event request" — payload validation (AC1-AC4).

The fixed "today" is 2026-09-15 (see ``tests/events/conftest.py``).
Decisions the AC left open are recorded in ``docs/adr/0001`` to ``0003``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

import pytest

from app.common.clock import local_today
from app.common.errors import ValidationError
from app.common.validation import load_or_raise
from app.modules.events import schemas
from app.modules.events.schemas import NAME_MAX_LENGTH, SubmitEventRequestSchema

pytestmark = pytest.mark.scrum_19

REQUIRED_FIELDS = ["name", "proposed_date", "start_time", "end_time", "expected_attendance"]


def _load(payload: Any, today: date) -> dict[str, Any]:
    return load_or_raise(SubmitEventRequestSchema(today=today), payload)


def _errors_for(payload: Any, today: date) -> dict[str, Any]:
    with pytest.raises(ValidationError) as exc_info:
        _load(payload, today)
    assert exc_info.value.status_code == 400
    return exc_info.value.details or {}


# --------------------------------------------------------------------------
# AC1 — every field can be supplied
# --------------------------------------------------------------------------


def test_full_payload_is_accepted_with_every_field(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    data = _load(valid_event_request_payload, today)

    assert data == {
        "name": "ConnectSphere Partner Summit",
        "purpose": "Annual showcase for partner organisations",
        "description": "Keynotes in the morning, breakout sessions after lunch.",
        "proposed_date": date(2026, 10, 15),
        "end_date": date(2026, 10, 15),
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "expected_attendance": 250,
        "venue_requirements": "Main hall with a stage and 3 breakout rooms",
        "accessibility_needs": "Step-free access and live captioning",
        "equipment_requirements": "2 projectors, PA system, 4 wireless mics",
        "registration_required": True,
    }


def test_only_required_fields_is_accepted_with_defaults(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    payload = {key: valid_event_request_payload[key] for key in REQUIRED_FIELDS}

    data = _load(payload, today)

    for key in schemas.OPTIONAL_TEXT_FIELDS:
        assert data[key] is None
    assert data["registration_required"] is False
    assert data["end_date"] == data["proposed_date"]


def test_text_is_trimmed_and_blank_optional_text_is_stored_as_null(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload["name"] = "  Partner Summit  "
    valid_event_request_payload["purpose"] = "   "
    valid_event_request_payload["description"] = ""
    valid_event_request_payload["accessibility_needs"] = None

    data = _load(valid_event_request_payload, today)

    assert data["name"] == "Partner Summit"
    assert data["purpose"] is None
    assert data["description"] is None
    assert data["accessibility_needs"] is None


@pytest.mark.parametrize("value", [False, True])
def test_registration_required_accepts_booleans(
    value: bool, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload["registration_required"] = value
    assert _load(valid_event_request_payload, today)["registration_required"] is value


@pytest.mark.parametrize("value", ["yes", "true", None])
def test_registration_required_rejects_non_booleans(
    value: Any, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload["registration_required"] = value
    assert "registration_required" in _errors_for(valid_event_request_payload, today)


@pytest.mark.parametrize("field", ["status", "reference", "organiser_id", "id"])
def test_server_controlled_fields_cannot_be_supplied(
    field: str, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload[field] = "anything"
    assert field in _errors_for(valid_event_request_payload, today)


# --------------------------------------------------------------------------
# AC2 — name, proposed date, start time, end time and attendance are required
# --------------------------------------------------------------------------


@pytest.mark.parametrize("missing_field", REQUIRED_FIELDS)
def test_missing_required_field_is_rejected(
    missing_field: str, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload.pop(missing_field)
    assert missing_field in _errors_for(valid_event_request_payload, today)


@pytest.mark.parametrize("null_field", REQUIRED_FIELDS)
def test_null_required_field_is_rejected(
    null_field: str, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload[null_field] = None
    assert null_field in _errors_for(valid_event_request_payload, today)


def test_all_missing_required_fields_are_reported_together(today: date) -> None:
    errors = _errors_for({}, today)
    assert set(REQUIRED_FIELDS) <= set(errors)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_name_is_rejected(
    blank: str, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload["name"] = blank
    errors = _errors_for(valid_event_request_payload, today)
    assert "Event name must not be blank." in errors["name"]


def test_name_at_max_length_is_accepted(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload["name"] = "x" * NAME_MAX_LENGTH
    assert _load(valid_event_request_payload, today)["name"] == "x" * NAME_MAX_LENGTH


def test_name_over_max_length_is_rejected(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload["name"] = "x" * (NAME_MAX_LENGTH + 1)
    assert "name" in _errors_for(valid_event_request_payload, today)


def test_attendance_of_one_is_accepted(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    """ADR-0003 boundary."""
    valid_event_request_payload["expected_attendance"] = 1
    assert _load(valid_event_request_payload, today)["expected_attendance"] == 1


@pytest.mark.parametrize("attendance", [0, -1])
def test_attendance_below_one_is_rejected(
    attendance: int, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload["expected_attendance"] = attendance
    errors = _errors_for(valid_event_request_payload, today)
    assert "Expected attendance must be at least 1." in errors["expected_attendance"]


@pytest.mark.parametrize("attendance", ["50", 50.5, 50.0, True])
def test_attendance_must_be_a_whole_number(
    attendance: Any, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload["expected_attendance"] = attendance
    assert "expected_attendance" in _errors_for(valid_event_request_payload, today)


@pytest.mark.parametrize("payload", [None, [], "string", 42])
def test_non_object_body_is_rejected(payload: Any, today: date) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _load(payload, today)
    assert exc_info.value.status_code == 400


# --------------------------------------------------------------------------
# AC3 — proposed date cannot be in the past (ADR-0001)
# --------------------------------------------------------------------------


def test_proposed_date_yesterday_is_rejected(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload.update(proposed_date="2026-09-14")
    errors = _errors_for(valid_event_request_payload, today)
    assert "Proposed date cannot be in the past." in errors["proposed_date"]


@pytest.mark.parametrize("proposed_date", ["2026-09-15", "2026-09-16"])
def test_proposed_date_today_or_later_is_accepted(
    proposed_date: str, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload.update(proposed_date=proposed_date)
    assert _load(valid_event_request_payload, today)["proposed_date"].isoformat() == proposed_date


@pytest.mark.parametrize("bad_date", ["15/10/2026", "2026-02-30", "tomorrow"])
def test_invalid_proposed_date_format_is_rejected(
    bad_date: str, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload["proposed_date"] = bad_date
    assert "proposed_date" in _errors_for(valid_event_request_payload, today)


def test_schema_defaults_to_today_in_business_timezone(
    monkeypatch: pytest.MonkeyPatch, valid_event_request_payload: dict[str, Any]
) -> None:
    monkeypatch.setattr(schemas, "local_today", lambda: date(2026, 10, 16))
    valid_event_request_payload.update(proposed_date="2026-10-15")

    with pytest.raises(ValidationError) as exc_info:
        load_or_raise(SubmitEventRequestSchema(), valid_event_request_payload)

    assert "proposed_date" in (exc_info.value.details or {})


@pytest.mark.parametrize(
    ("utc_now", "expected_today"),
    [
        # Singapore is UTC+8, so the local date changes at 16:00 UTC.
        (datetime(2026, 9, 15, 15, 59, tzinfo=timezone.utc), date(2026, 9, 15)),
        (datetime(2026, 9, 15, 16, 0, tzinfo=timezone.utc), date(2026, 9, 16)),
    ],
)
def test_local_today_uses_singapore_time(utc_now: datetime, expected_today: date) -> None:
    assert local_today(utc_now) == expected_today


def test_local_today_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        # Naive on purpose: rejecting it is what this test asserts.
        local_today(datetime(2026, 9, 15, 12, 0))  # noqa: DTZ001


# --------------------------------------------------------------------------
# AC4 — the event cannot end before it starts (ADR-0002)
# --------------------------------------------------------------------------


def test_end_time_before_start_time_on_same_day_is_rejected(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload.update(start_time="14:00", end_time="13:00")
    errors = _errors_for(valid_event_request_payload, today)
    assert "Event must end after it starts." in errors["end_time"]


def test_end_time_equal_to_start_time_is_rejected(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload.update(start_time="14:00", end_time="14:00")
    assert "end_time" in _errors_for(valid_event_request_payload, today)


def test_end_time_one_minute_after_start_is_accepted(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload.update(start_time="14:00", end_time="14:01")
    assert _load(valid_event_request_payload, today)["end_time"] == time(14, 1)


def test_overnight_event_with_next_day_end_date_is_accepted(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload.update(
        proposed_date="2026-10-15", end_date="2026-10-16", start_time="22:00", end_time="02:00"
    )
    data = _load(valid_event_request_payload, today)
    assert data["end_date"] == date(2026, 10, 16)


def test_overnight_times_without_end_date_are_rejected(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    """Without ``end_date`` the event is same-day, so 22:00 → 02:00 ends early."""
    valid_event_request_payload.update(start_time="22:00", end_time="02:00")
    assert "end_time" in _errors_for(valid_event_request_payload, today)


def test_multi_day_event_is_accepted(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    """ADR-0002 sets no maximum duration."""
    valid_event_request_payload.update(
        proposed_date="2026-10-15", end_date="2026-10-17", start_time="17:00", end_time="09:00"
    )
    assert _load(valid_event_request_payload, today)["end_date"] == date(2026, 10, 17)


def test_same_times_on_later_end_date_is_accepted(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload.update(
        proposed_date="2026-10-15", end_date="2026-10-16", start_time="14:00", end_time="14:00"
    )
    assert _load(valid_event_request_payload, today)["end_date"] == date(2026, 10, 16)


def test_end_date_before_proposed_date_is_rejected(
    valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload.update(proposed_date="2026-10-15", end_date="2026-10-14")
    errors = _errors_for(valid_event_request_payload, today)
    assert "End date cannot be before the proposed date." in errors["end_date"]


@pytest.mark.parametrize("end_date", ["2026-10-15", None])
def test_end_date_same_as_proposed_date_or_null_means_same_day(
    end_date: str | None, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload.update(proposed_date="2026-10-15", end_date=end_date)
    assert _load(valid_event_request_payload, today)["end_date"] == date(2026, 10, 15)


@pytest.mark.parametrize("field", ["start_time", "end_time"])
@pytest.mark.parametrize("bad_time", ["25:00", "9am", "noon"])
def test_invalid_time_format_is_rejected(
    field: str, bad_time: str, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload[field] = bad_time
    assert field in _errors_for(valid_event_request_payload, today)


@pytest.mark.parametrize("field", ["start_time", "end_time"])
def test_time_with_timezone_offset_is_rejected(
    field: str, valid_event_request_payload: dict[str, Any], today: date
) -> None:
    valid_event_request_payload[field] = "12:00:00+08:00"
    errors = _errors_for(valid_event_request_payload, today)
    assert "Time must not include a timezone offset." in errors[field]
