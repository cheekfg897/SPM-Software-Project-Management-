"""Notifications module — in-app notifications about events (SCRUM-28).

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.notifications.services.notify_users`
* :class:`app.modules.notifications.services.EventSummary`
* :class:`app.modules.notifications.services.NotificationKind` (re-exported from
  ``models``, so callers never import the models)
"""

from __future__ import annotations

from flask import Flask


def register(app: Flask) -> None:
    """Attach the notifications blueprint to ``app``."""
    from app.modules.notifications.routes import bp

    app.register_blueprint(bp)
