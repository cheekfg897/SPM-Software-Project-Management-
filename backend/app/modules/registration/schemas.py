"""Marshmallow schemas for the registration module.

``CatalogueQuerySchema`` and ``MyRegistrationsQuerySchema`` read query strings, which
arrive as text; the others write the responses ADR-0032 and ADR-0044 describe. Output
schemas mark every field ``dump_only`` and show no internal user ids.
"""

from __future__ import annotations

import enum
from typing import Any

from marshmallow import (
    Schema,
    ValidationError as MarshmallowValidationError,
    fields,
    post_load,
    validate,
    validates_schema,
)

from app.common.clock import as_utc
from app.common.fields import BusinessDateTime
from app.modules.registration.models import RegistrationStatus

DEFAULT_PAGE_SIZE = 12
MAX_PAGE_SIZE = 50

NOT_A_DATE_TIME_MESSAGE = "Not a valid date-time."


class CatalogueWindow(str, enum.Enum):
    """A preset window on the events' start, resolved in business time (ADR-0032)."""

    UPCOMING = "upcoming"
    TODAY = "today"
    THIS_WEEK = "this_week"
    THIS_WEEKEND = "this_weekend"


class CatalogueQuerySchema(Schema):
    """The catalogue's query parameters, all optional (ADR-0032)."""

    q = fields.String()
    when = fields.Enum(CatalogueWindow, by_value=True)
    starts_from = fields.DateTime(format="iso", error_messages={"invalid": NOT_A_DATE_TIME_MESSAGE})
    starts_to = fields.DateTime(format="iso", error_messages={"invalid": NOT_A_DATE_TIME_MESSAGE})
    page = fields.Integer(
        load_default=1, validate=validate.Range(min=1, error="Must be at least 1.")
    )
    page_size = fields.Integer(
        load_default=DEFAULT_PAGE_SIZE,
        validate=validate.Range(
            min=1, max=MAX_PAGE_SIZE, error=f"Must be between 1 and {MAX_PAGE_SIZE}."
        ),
    )

    @validates_schema
    def check_window(self, data: dict[str, Any], **kwargs: Any) -> None:
        """Refuse a preset with a custom range, and a range that runs backwards."""
        starts_from = data.get("starts_from")
        starts_to = data.get("starts_to")
        has_range = starts_from is not None or starts_to is not None
        if "when" in data and has_range:
            raise MarshmallowValidationError(
                "Send either a preset or a custom range, not both.", field_name="when"
            )
        runs_backwards = (
            starts_from is not None
            and starts_to is not None
            and as_utc(starts_to) < as_utc(starts_from)
        )
        if runs_backwards:
            raise MarshmallowValidationError("Must be after starts_from.", field_name="starts_to")

    @post_load
    def trim_search(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Ignore spaces around the search text."""
        if "q" in data:
            data["q"] = data["q"].strip()
        return data


class PublicEventSchema(Schema):
    """What anyone may know of an event: its name, description and times (SCRUM-52).

    Nothing from the event's internal planning (SCRUM-21). The catalogue and an
    Attendee's own event page both start from it.
    """

    id = fields.Integer(dump_only=True)
    reference = fields.String(dump_only=True)
    name = fields.String(dump_only=True)
    description = fields.String(dump_only=True)
    starts_at = BusinessDateTime(dump_only=True)
    ends_at = BusinessDateTime(dump_only=True)


class CatalogueEventSchema(PublicEventSchema):
    """One event in the catalogue (ADR-0032)."""

    # TODO: the booked venue's id and name, once the venue stack lets the events
    # module find it (SCRUM-42, SCRUM-43; ADR-0032).
    venue = fields.Constant(None, dump_only=True)
    capacity = fields.Integer(dump_only=True)
    places_left = fields.Integer(dump_only=True)
    is_full = fields.Boolean(dump_only=True)
    is_registered = fields.Boolean(dump_only=True)


class CataloguePageSchema(Schema):
    """One page of the catalogue, with the totals the frontend shows as they are."""

    items = fields.List(fields.Nested(CatalogueEventSchema), dump_only=True)
    page = fields.Integer(dump_only=True)
    page_size = fields.Integer(dump_only=True)
    total = fields.Integer(dump_only=True)
    total_pages = fields.Integer(dump_only=True)


class BookedVenueSchema(Schema):
    """A venue the event is booked at: its name and where it is (SCRUM-24 AC11)."""

    name = fields.String(dump_only=True)
    location = fields.String(dump_only=True)


class MyRegisteredEventSchema(PublicEventSchema):
    """An event the attendee registered for, as its page shows it (ADR-0109).

    The catalogue's public fields, the event's status and booked venues, the
    registration, when withdrawals close and whether Withdraw is offered.
    """

    event_status = fields.String(dump_only=True)
    venues = fields.List(fields.Nested(BookedVenueSchema), dump_only=True)
    status = fields.Enum(RegistrationStatus, by_value=True, dump_only=True)
    registered_at = BusinessDateTime(dump_only=True)
    withdrawn_at = BusinessDateTime(dump_only=True)
    withdrawals_close_at = BusinessDateTime(dump_only=True)
    can_withdraw = fields.Boolean(dump_only=True)


class RegistrationSchema(Schema):
    """A registration just made (ADR-0032)."""

    id = fields.Integer(dump_only=True)
    event_id = fields.Integer(attribute="event_request_id", dump_only=True)
    status = fields.Enum(RegistrationStatus, by_value=True, dump_only=True)
    registered_at = BusinessDateTime(dump_only=True)
    withdrawn_at = BusinessDateTime(dump_only=True)


class RegistrantSchema(Schema):
    """One registrant: their name, email, date and status (SCRUM-55 AC3)."""

    name = fields.String(dump_only=True)
    email = fields.String(dump_only=True)
    registered_at = BusinessDateTime(dump_only=True)
    status = fields.Enum(RegistrationStatus, by_value=True, dump_only=True)


class RegistrantListSchema(Schema):
    """An event's registrants and the count against its capacity (SCRUM-55)."""

    capacity = fields.Integer(dump_only=True, allow_none=True)
    registered_count = fields.Integer(dump_only=True)
    places_left = fields.Integer(dump_only=True, allow_none=True)
    items = fields.List(fields.Nested(RegistrantSchema), dump_only=True)


class MyEventsWindow(str, enum.Enum):
    """Which of an attendee's events to list: not yet ended, or ended (ADR-0044)."""

    UPCOMING = "upcoming"
    PAST = "past"


class MyRegistrationsQuerySchema(Schema):
    """The attendee's list's query: ``when``, upcoming by default (ADR-0044)."""

    when = fields.Enum(MyEventsWindow, by_value=True, load_default=MyEventsWindow.UPCOMING)


class MyRegistrationSchema(Schema):
    """One of the attendee's own registrations, with the event it is for.

    ``reference`` opens the event's page (SCRUM-24 AC11, ADR-0109).
    """

    event_id = fields.Integer(dump_only=True)
    reference = fields.String(dump_only=True)
    name = fields.String(dump_only=True)
    starts_at = BusinessDateTime(dump_only=True)
    ends_at = BusinessDateTime(dump_only=True)
    event_status = fields.String(dump_only=True)
    status = fields.Enum(RegistrationStatus, by_value=True, dump_only=True)
    registered_at = BusinessDateTime(dump_only=True)
    withdrawn_at = BusinessDateTime(dump_only=True)
