"""Request/response schemas for the events module (marshmallow).

Rules for SCRUM-19 "Submit an event request". Where the acceptance criteria
were ambiguous, the choice is recorded as an ADR in ``docs/adr/``:

* ADR-0001: a proposed date before today (business timezone) is rejected.
* ADR-0002: the event must end strictly after it starts; overnight events use
  the optional ``end_date``.
* ADR-0003: expected attendance is a whole number of at least 1.

SCRUM-37 adds the equipment lines recorded on a request (ADR-0019), SCRUM-87 the
coordinator a request is reassigned to (ADR-0021), SCRUM-38 the list of lines still
awaiting Technical Support (ADR-0022), and SCRUM-20 :class:`SaveDraftSchema`, which
:class:`SubmitEventRequestSchema` extends with the rules that only apply once a
request is submitted (ADR-0024). ``_EventTimingSchema`` holds the date rules that
depend on today (ADR-0001), shared by submitting and editing a request.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from marshmallow import (
    Schema,
    ValidationError as MarshmallowValidationError,
    fields,
    post_load,
    validate,
    validates,
    validates_schema,
)

from app.common.clock import local_today
from app.common.fields import WholeNumber
from app.modules.events.models import NAME_MAX_LENGTH, EquipmentLineStatus, EventRequestStatus

#: Free-text fields a request may leave out. Blank values are stored as null.
OPTIONAL_TEXT_FIELDS = (
    "purpose",
    "description",
    "venue_requirements",
    "accessibility_needs",
    "equipment_requirements",
)


#: Shared by both schemas, so a draft's attendance is checked the same way once
#: submission requires it too.
_ATTENDANCE_AT_LEAST_ONE = validate.Range(min=1, error="Expected attendance must be at least 1.")


def _not_blank(value: str) -> None:
    if not value.strip():
        raise MarshmallowValidationError("Event name must not be blank.")


def _no_timezone_offset(value: time) -> None:
    # Times are in the business timezone. An offset would also make the start/end
    # comparison fail (naive vs aware datetimes). Marshmallow skips field validators
    # for a null value, so a draft may leave a time empty.
    if value.tzinfo is not None:
        raise MarshmallowValidationError("Time must not include a timezone offset.")


def _optional_text() -> fields.String:
    return fields.String(required=False, allow_none=True, load_default=None)


def _optional_date() -> fields.Date:
    return fields.Date(required=False, allow_none=True, load_default=None)


def _optional_time() -> fields.Time:
    return fields.Time(
        required=False, allow_none=True, load_default=None, validate=_no_timezone_offset
    )


def _required_time() -> fields.Time:
    return fields.Time(required=True, validate=_no_timezone_offset)


def _blank_as_none(value: str | None) -> str | None:
    """A trimmed value, or ``None`` for a blank or absent one."""
    if value is None:
        return None
    return value.strip() or None


def _check_time_window(
    proposed_date: date, end_date: date, start_time: time, end_time: time
) -> None:
    """Raise if the window is invalid: end before start (ADR-0002)."""
    if end_date < proposed_date:
        raise MarshmallowValidationError(
            "End date cannot be before the proposed date.", field_name="end_date"
        )

    starts = datetime.combine(proposed_date, start_time)
    ends = datetime.combine(end_date, end_time)
    if ends <= starts:
        raise MarshmallowValidationError("Event must end after it starts.", field_name="end_time")


class _EventTimingSchema(Schema):
    """The date rule that depends on today, shared by submitting and editing a request.

    A proposed date must not be in the past (ADR-0001). A draft doesn't use this
    schema: it may hold a past date until it is submitted (ADR-0024).

    Args:
        today: The date "in the past" is measured against. Defaults to today
            in the business timezone; tests pass a fixed date.
    """

    def __init__(self, *, today: date | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._today = today

    @property
    def today(self) -> date:
        """The reference date for the "not in the past" rule."""
        return self._today if self._today is not None else local_today()

    @validates("proposed_date")
    def _proposed_date_not_in_past(self, value: date, **_: Any) -> None:
        if value < self.today:
            raise MarshmallowValidationError("Proposed date cannot be in the past.")


class SaveDraftSchema(Schema):
    """Payload to save a draft or edit one (SCRUM-20 AC1, AC3).

    Only ``name`` is required; every other field is optional and, when it is sent,
    is checked on its own. Rules that compare two fields, or depend on today
    (ADR-0001, ADR-0002), wait until the request is submitted (ADR-0024): a draft may
    already hold a date in the past or an end time before the start, since it isn't
    going ahead yet. Fields the server controls (``status``, ``reference``,
    ``organiser_id``) are not declared, so sending them is rejected as an unknown
    field. Editing a draft loads this schema with ``partial`` set to every one of
    its field names, so a request may send any subset of them.
    """

    name = fields.String(
        required=True,
        validate=[
            _not_blank,
            validate.Length(
                max=NAME_MAX_LENGTH,
                error=f"Event name must be at most {NAME_MAX_LENGTH} characters.",
            ),
        ],
    )
    purpose = _optional_text()
    description = _optional_text()
    proposed_date = _optional_date()
    end_date = _optional_date()
    start_time = _optional_time()
    end_time = _optional_time()
    expected_attendance = WholeNumber(
        required=False, allow_none=True, load_default=None, validate=_ATTENDANCE_AT_LEAST_ONE
    )
    venue_requirements = _optional_text()
    accessibility_needs = _optional_text()
    equipment_requirements = _optional_text()
    registration_required = fields.Boolean(
        required=False, load_default=False, truthy={True}, falsy={False}
    )

    @post_load
    def _normalise(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        """Trim the fields that were actually sent; a field left out stays left out.

        A partial edit (AC3) puts only the sent keys in ``data``, so checking
        ``key in data`` before touching it never invents a field the caller did not
        send, and a full save (AC1) trims every one it fills in.
        """
        if "name" in data:
            data["name"] = data["name"].strip()
        for key in OPTIONAL_TEXT_FIELDS:
            if key in data:
                data[key] = _blank_as_none(data[key])
        return data


class SubmitEventRequestSchema(_EventTimingSchema, SaveDraftSchema):
    """Payload for ``POST /api/events/requests`` and submitting a draft (SCRUM-19).

    Takes its fields from :class:`SaveDraftSchema`, makes the ones a submission cannot
    do without required, and adds the rules that only make sense once every one of
    them is present: the proposed date must not be in the past (ADR-0001, from
    :class:`_EventTimingSchema`), and the event must end after it starts (ADR-0002).
    """

    proposed_date = fields.Date(required=True)
    start_time = _required_time()
    end_time = _required_time()
    expected_attendance = WholeNumber(required=True, validate=_ATTENDANCE_AT_LEAST_ONE)

    @validates_schema
    def _ends_after_it_starts(self, data: dict[str, Any], **_: Any) -> None:
        # Only runs when every field passed its own validation, so the
        # required keys are guaranteed to be present.
        proposed_date: date = data["proposed_date"]
        end_date: date = data.get("end_date") or proposed_date
        _check_time_window(proposed_date, end_date, data["start_time"], data["end_time"])

    @post_load
    def _end_date_defaults_to_proposed_date(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        """Default ``end_date`` to ``proposed_date`` when it was not sent (ADR-0002).

        Runs alongside :meth:`SaveDraftSchema._normalise`, which this schema also
        inherits; only submission defaults ``end_date`` like this (ADR-0024 20-8), so
        a draft keeps ``end_date`` exactly as sent.
        """
        if data.get("end_date") is None:
            data["end_date"] = data["proposed_date"]
        return data


class EventRequestSchema(Schema):
    """Public representation of an event request (AC5).

    The internal ``id``, ``organiser_id`` and ``coordinator_id`` are not exposed:
    ``reference`` is the identifier clients use (ADR-0004).
    """

    reference = fields.String(dump_only=True)
    status = fields.Enum(EventRequestStatus, by_value=True, dump_only=True)
    name = fields.String(dump_only=True)
    purpose = fields.String(dump_only=True, allow_none=True)
    description = fields.String(dump_only=True, allow_none=True)
    proposed_date = fields.Date(dump_only=True, allow_none=True)
    end_date = fields.Date(dump_only=True, allow_none=True)
    start_time = fields.Time(dump_only=True, allow_none=True)
    end_time = fields.Time(dump_only=True, allow_none=True)
    expected_attendance = fields.Integer(dump_only=True, allow_none=True)
    venue_requirements = fields.String(dump_only=True, allow_none=True)
    accessibility_needs = fields.String(dump_only=True, allow_none=True)
    equipment_requirements = fields.String(dump_only=True, allow_none=True)
    registration_required = fields.Boolean(dump_only=True)
    created_at = fields.DateTime(dump_only=True, allow_none=True)


class CoordinatorContactSchema(Schema):
    """The assigned coordinator as the organiser sees them (SCRUM-30 AC3).

    Name and contact details only: never their id or role.
    """

    full_name = fields.String(dump_only=True)
    email = fields.Email(dump_only=True)


#: What the equipment list says about its event: when it is, so Technical Support know
#: by when the equipment is needed (SCRUM-37, ADR-0019). Dumped with
#: :class:`EventRequestSchema`, so the names and formats match the request itself.
EQUIPMENT_EVENT_FIELDS = (
    "reference",
    "name",
    "proposed_date",
    "end_date",
    "start_time",
    "end_time",
)


class ReassignCoordinatorSchema(Schema):
    """Payload for ``POST /api/events/requests/<reference>/reassign`` (SCRUM-87).

    The new coordinator is named by email, since user ids are never shown to other
    users (ADR-0021).
    """

    coordinator_email = fields.Email(required=True)


class EditEquipmentLineSchema(Schema):
    """Payload for adding (``POST``) or editing (``PATCH``) an equipment line.

    SCRUM-37 AC1-AC3. Edits are loaded with ``partial`` set to this schema's field
    names, so any field may be left out; a field that is sent is checked the same way
    as on add. ``status`` is server-controlled and not declared, so sending it is an
    unknown field.
    """

    equipment_type_id = WholeNumber(
        required=True,
        validate=validate.Range(min=1, error="equipment_type_id must be a positive number."),
    )
    quantity = WholeNumber(
        required=True, validate=validate.Range(min=1, error="Quantity must be at least 1.")
    )
    notes = fields.String(allow_none=True, load_default=None)

    @post_load
    def _normalise(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        # Only a key that is present is touched, so this is safe for partial edits.
        if data.get("notes") is not None:
            data["notes"] = data["notes"].strip() or None
        return data


class EquipmentLineSchema(Schema):
    """One equipment line as the API shows it (SCRUM-37 AC4).

    ``id`` is exposed because edit and remove address a line by it. The event's
    internal id is not: a line is always read under the event's reference.
    """

    id = fields.Integer(dump_only=True)
    equipment_type_id = fields.Integer(dump_only=True)
    quantity = fields.Integer(dump_only=True)
    notes = fields.String(dump_only=True, allow_none=True)
    status = fields.Enum(EquipmentLineStatus, by_value=True, dump_only=True)


class EquipmentAwaitingActionSchema(Schema):
    """One event's equipment still awaiting Technical Support (SCRUM-38 AC2, ADR-0022).

    The event is dumped with the same fields as the SCRUM-37 equipment list, so its
    name, date and times read the same in both places.
    """

    event = fields.Nested(
        EventRequestSchema(only=EQUIPMENT_EVENT_FIELDS), attribute="event_request", dump_only=True
    )
    equipment_lines = fields.Nested(EquipmentLineSchema, many=True, dump_only=True)
    days_remaining = fields.Integer(dump_only=True)


class EventRequestDetailSchema(EventRequestSchema):
    """An event request as its own record shows it: the summary and its equipment lines.

    SCRUM-37 AC4. The list of requests keeps :class:`EventRequestSchema`, so listing
    never loads every request's lines.
    """

    equipment_lines = fields.Nested(EquipmentLineSchema, many=True, dump_only=True)
