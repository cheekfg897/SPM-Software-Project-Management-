"""ConnectSphere backend — application factory.

Architecture: a *modularised monolith*. One deployable Flask app, internally
split into self-contained modules under ``app/modules/<name>/``. Each module
owns its models, routes, schemas, services and permission rules, and exposes a
single ``register(app)`` hook. Modules only talk to each other through service
functions, never by importing another module's models directly.
"""

from __future__ import annotations

import logging

from flask import Flask

from app.common.errors import register_error_handlers
from app.common.health import register_health_check
from app.config import get_config
from app.extensions import db, jwt, migrate


def _configure_logging(app: Flask) -> None:
    """Ensure INFO-level logs (incl. authorization failures) reach the console."""
    if not app.logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)


def _init_extensions(app: Flask) -> None:
    """Bind the shared extension instances to this app."""
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)


def _register_modules(app: Flask) -> None:
    """Register every bounded-context module.

    New modules (equipment, ...) are added here in later
    sprints by importing their ``register`` function. Nothing else in the
    app needs to change.
    """
    from app.modules import auth, events, venue

    auth.register(app)
    events.register(app)
    venue.register(app)


def create_app(config_name: str | None = None) -> Flask:
    """Build and configure the Flask application.

    Args:
        config_name: One of ``development``, ``testing``, ``production``.
            Defaults to the ``FLASK_ENV`` environment variable, then
            ``development``.

    Returns:
        A fully configured :class:`flask.Flask` instance.
    """
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    _configure_logging(app)
    _init_extensions(app)
    _register_modules(app)
    register_error_handlers(app)
    register_health_check(app)

    return app
