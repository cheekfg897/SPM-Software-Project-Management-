"""Equipment module — the equipment catalogue, its availability and reservations.

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.equipment.services.get_equipment_type`
* :func:`app.modules.equipment.services.list_equipment_types`
* :func:`app.modules.equipment.services.equipment_availability_for_event`
* :func:`app.modules.equipment.services.list_reservations_for_event`
* :func:`app.modules.equipment.services.mark_event_reservations_for_reassessment`
  and the other SCRUM-60 reassessment functions the events module calls (ADR-0114)
"""

from __future__ import annotations

from flask import Flask


def register(app: Flask) -> None:
    """Attach the equipment blueprint to ``app``."""
    from app.modules.equipment.routes import bp

    app.register_blueprint(bp)
