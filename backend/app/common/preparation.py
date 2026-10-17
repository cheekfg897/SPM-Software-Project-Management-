"""The preparation details shared by venue bookings and equipment reservations.

Venue Staff record how far a booking's set-up has got (SCRUM-84, ADR-0049), and
Technical Support a reservation's (SCRUM-85, ADR-0050). Both take the same notes and
wait for the same safety approval, so those rules live here. Each module keeps its own
``PreparationStatus`` enum, because a module never imports another module's models, and
adds it to :class:`PreparationNotesSchema` as its ``status`` field.
"""

from __future__ import annotations

from typing import Any

from marshmallow import (
    Schema,
    ValidationError as MarshmallowValidationError,
    fields,
    post_load,
    validates,
)

from app.common.validation import not_blank

#: Longest preparation note. The columns are ``Text``, so this is an API rule.
PREPARATION_NOTES_MAX_LENGTH = 1000

PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE = (
    "Preparation details can't be recorded until the Safety Officer has approved"
    " the event's Operational Safety Check."
)


class PreparationNotesSchema(Schema):
    """The ``notes`` of a preparation update: optional, never blank, and trimmed.

    Notes left out are cleared, since each update states the whole picture.
    """

    notes = fields.String(allow_none=True, load_default=None, validate=not_blank)

    @validates("notes")
    def _notes_fit(self, value: str | None, **_: Any) -> None:
        # Marshmallow also runs this on the default of notes left out.
        if value is None:
            return
        # Measured once trimmed, since that's what is stored.
        if len(value.strip()) > PREPARATION_NOTES_MAX_LENGTH:
            raise MarshmallowValidationError(
                f"Notes must be at most {PREPARATION_NOTES_MAX_LENGTH} characters."
            )

    @post_load
    def _trim_notes(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        if data["notes"] is not None:
            data["notes"] = data["notes"].strip()
        return data
