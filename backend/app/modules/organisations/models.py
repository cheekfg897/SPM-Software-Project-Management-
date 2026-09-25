"""SQLAlchemy models owned by the organisations module.

Other modules must **not** import these directly; they go through the
functions in :mod:`app.modules.organisations.services`. Tables that point at a
client organisation (``users``, ``event_requests``) use a database-level foreign
key only.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db

NAME_MAX_LENGTH = 120
CONTACT_NAME_MAX_LENGTH = 120
CONTACT_EMAIL_MAX_LENGTH = 255
CONTACT_PHONE_MAX_LENGTH = 30

#: Name of the unique constraint on ``name``: two organisations can't share a name
#: (ADR-0013).
NAME_UNIQUE_CONSTRAINT = "uq_client_organisations_name"


class ClientOrganisation(db.Model):  # type: ignore[name-defined]
    """A client organisation that Event Organisers belong to (SCRUM-66 AC1)."""

    __tablename__ = "client_organisations"
    __table_args__ = (UniqueConstraint("name", name=NAME_UNIQUE_CONSTRAINT),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(CONTACT_NAME_MAX_LENGTH), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(CONTACT_EMAIL_MAX_LENGTH), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(
        String(CONTACT_PHONE_MAX_LENGTH), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ClientOrganisation id={self.id} name={self.name!r}>"
