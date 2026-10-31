"""Response schemas for the notifications module (marshmallow).

Notifications are only ever written by services, never from a request body, so
there are no input schemas. The output schema is ``dump_only`` and defines exactly
what the API returns: nothing that identifies another user or an internal row.
"""

from __future__ import annotations

from marshmallow import Schema, fields

from app.common.fields import BusinessDateTime
from app.modules.notifications.models import Notification, NotificationKind

#: What each kind says happened (SCRUM-28 AC1). Every kind must have an entry.
MESSAGE_BY_KIND: dict[NotificationKind, str] = {
    NotificationKind.EVENT_REQUEST_SUBMITTED: "A new event request was submitted.",
    NotificationKind.COORDINATOR_ASSIGNED: "You have been assigned to coordinate this event.",
    NotificationKind.EQUIPMENT_REQUESTED: "Equipment was requested for an event.",
    NotificationKind.SIGNIFICANT_CHANGE: (
        "An event you have arrangements for has changed significantly. Please check they still fit."
    ),
    NotificationKind.EVENT_REQUEST_APPROVED: "Your event request was approved.",
    NotificationKind.EVENT_REQUEST_REJECTED: "Your event request was rejected.",
    NotificationKind.CLARIFICATION_REQUESTED: (
        "Your Event Coordinator has asked for clarification on your event request."
    ),
    NotificationKind.CLARIFICATION_ANSWERED: (
        "The organiser has answered your request for clarification."
    ),
    NotificationKind.REQUEST_ASSIGNED: (
        "An Event Coordinator has been assigned to your event request."
    ),
    NotificationKind.VENUE_BOOKING_REQUESTED: (
        "A venue booking request is waiting for your decision."
    ),
    NotificationKind.VENUE_BOOKING_APPROVED: "Your venue booking request was approved.",
    NotificationKind.VENUE_BOOKING_REJECTED: "Your venue booking request was rejected.",
    NotificationKind.VENUE_HOLD_PLACED: "A venue is being held tentatively for your event.",
    NotificationKind.VENUE_HOLD_EXPIRY_CHANGED: (
        "The expiry of a tentative venue hold on your event has changed."
    ),
    NotificationKind.VENUE_HOLD_EXPIRING: (
        "A tentative venue hold on your event expires within 24 hours."
    ),
    NotificationKind.VENUE_HOLD_EXPIRED: (
        "A tentative venue hold on your event has expired, so the venue was released."
    ),
    NotificationKind.EQUIPMENT_RESERVED: "Equipment was reserved for an event.",
    NotificationKind.REQUEST_QUEUED_FOR_LEAD: (
        "A new event request is waiting in the unassigned queue."
    ),
    NotificationKind.EQUIPMENT_OUTCOME_RECORDED: (
        "Technical Support has recorded the outcome of your equipment request."
    ),
    NotificationKind.SAFETY_REVIEW_REQUESTED: "An event is waiting for your safety review.",
    NotificationKind.SAFETY_CHECK_APPROVED: "The Safety Officer approved your event.",
    NotificationKind.SAFETY_CHECK_REJECTED: (
        "The Safety Officer rejected your event. It is back in planning."
    ),
    NotificationKind.SAFETY_CHANGES_REQUESTED: (
        "The Safety Officer requested changes to your event. It is back in planning."
    ),
    NotificationKind.EVENT_CONFIRMED: "Your event has been confirmed.",
    NotificationKind.ALTERNATIVE_VENUE_NEEDED: (
        "A venue booked for your event is unavailable. The event needs an alternative venue."
    ),
    NotificationKind.VENUE_BOOKING_CONFLICTING: (
        "A confirmed booking is now Conflicting after a venue's setup or turnaround time changed."
    ),
    NotificationKind.VENUE_AVAILABLE_AGAIN: (
        "A venue that was unavailable for your event is available again."
    ),
    NotificationKind.VENUE_BOOKING_RELEASED: (
        "A venue booking or hold was released because its event was rejected during planning."
    ),
    NotificationKind.SAFETY_REVIEW_EVENT_CHANGED: (
        "An event in Safety Review changed significantly."
    ),
    NotificationKind.REPLACEMENT_VENUE_APPROVED: "A replacement venue was approved for your event.",
    NotificationKind.VENUE_BOOKING_RECONFIRMED: (
        "Venue Staff reconfirmed a venue booking for your event after a change."
    ),
    NotificationKind.CHANGE_REQUEST_RAISED: (
        "The organiser has requested a change to an event you coordinate."
    ),
    NotificationKind.CHANGE_REQUEST_WITHDRAWN: (
        "The organiser has withdrawn their change request for an event you coordinate."
    ),
    NotificationKind.VENUE_BOOKING_CANCELLED: (
        "The event's coordinator cancelled a venue booking, so the venue is free again."
    ),
    NotificationKind.SAFETY_REVIEW_VENUE_CANCELLED: (
        "A venue was dropped from an event in Safety Review."
    ),
}

#: Where a notification links to: the event's page, found by its reference
#: (ADR-0004, ADR-0015).
EVENT_LINK_TEMPLATE = "/events/{reference}"


class NotificationSchema(Schema):
    """Public representation of a notification (SCRUM-28 AC1).

    Times are shown in business time (ADR-0009).
    """

    id = fields.Integer(dump_only=True)
    kind = fields.Enum(NotificationKind, by_value=True, dump_only=True)
    message = fields.Method("get_message", dump_only=True)
    event_reference = fields.String(dump_only=True)
    event_name = fields.String(dump_only=True)
    link = fields.Method("get_link", dump_only=True)
    created_at = BusinessDateTime(dump_only=True)
    read_at = BusinessDateTime(dump_only=True, allow_none=True)
    #: More about what happened, such as the reason for a decision (SCRUM-31 AC10).
    detail = fields.String(dump_only=True, allow_none=True)

    def get_message(self, notification: Notification) -> str:
        """What happened, in words."""
        return MESSAGE_BY_KIND[notification.kind]

    def get_link(self, notification: Notification) -> str:
        """Where to open the event."""
        return EVENT_LINK_TEMPLATE.format(reference=notification.event_reference)
