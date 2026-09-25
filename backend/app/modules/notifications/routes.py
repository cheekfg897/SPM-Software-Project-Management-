"""HTTP routes for the notifications module — ``/api/notifications/*``.

Routes stay thin: call a service with the caller's id, serialise the result. Every
route reads or changes only the caller's own notifications, so any signed-in user
may call them (SCRUM-28 AC2). Error responses come from the handlers in
:mod:`app.common.errors`.
"""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify

from app.common.decorators import requires_auth
from app.modules.notifications.schemas import NotificationSchema
from app.modules.notifications.services import (
    count_unread_notifications,
    list_notifications_for_recipient,
    mark_notification_read,
)

bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")

_notification_schema = NotificationSchema()


@bp.get("")
@requires_auth
def list_my_notifications() -> tuple[Response, int]:
    """List the caller's own notifications, newest first (SCRUM-28 AC2)."""
    notifications = list_notifications_for_recipient(g.current_user_id)
    return (
        jsonify({"notifications": _notification_schema.dump(notifications, many=True)}),
        200,
    )


@bp.get("/unread-count")
@requires_auth
def unread_count() -> tuple[Response, int]:
    """How many of the caller's notifications are unread (SCRUM-28 AC5)."""
    return jsonify({"unread_count": count_unread_notifications(g.current_user_id)}), 200


@bp.post("/<int:notification_id>/read")
@requires_auth
def mark_read(notification_id: int) -> tuple[Response, int]:
    """Mark one of the caller's notifications read (SCRUM-28 AC4).

    Someone else's notification is a ``404``, the same as a missing one (ADR-0015).
    """
    notification = mark_notification_read(notification_id, g.current_user_id)
    return jsonify(_notification_schema.dump(notification)), 200
