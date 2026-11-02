"""Health endpoint — ``GET /health``.

Answers two questions in one call: is the app serving requests, and can it
reach its database. Deployment probes, a docker-compose healthcheck and the
smoke-test step in CI all read it.

That CI step proves the running app answers on a real database, but it only
ever sees a working one. ``tests/common/test_health.py`` checks both answers,
including the ``503`` an outage must give.

The body is a status document rather than the ``app.common.errors`` envelope:
probes read the status code, and this endpoint sits outside the ``/api``
contract.
"""

from __future__ import annotations

from flask import Blueprint, Flask, Response, current_app, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

bp = Blueprint("health", __name__)


@bp.get("/health")
def health() -> tuple[Response, int]:
    """Report whether the database answers, as ``200`` or ``503``.

    A probe that only proved the process was alive would stay green through
    exactly the outage worth paging for, so this spends one round trip.
    """
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        current_app.logger.warning("Health check could not reach the database: %s", exc)
        return jsonify({"status": "unhealthy", "database": "unreachable"}), 503
    return jsonify({"status": "ok", "database": "ok"}), 200


def register_health_check(app: Flask) -> None:
    """Attach the health blueprint, the same way every module attaches its own."""
    app.register_blueprint(bp)
