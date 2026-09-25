"""Equipment module — the equipment catalogue.

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.equipment.services.get_equipment_type`
* :func:`app.modules.equipment.services.list_equipment_types`
"""

from __future__ import annotations

from flask import Flask


def register(app: Flask) -> None:
    """Attach the equipment blueprint to ``app``."""
    from app.modules.equipment.routes import bp

    app.register_blueprint(bp)
