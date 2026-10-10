"""SQLAlchemy models owned by the auth module.

Other modules must **not** import ``User`` directly; they go through the
functions in :mod:`app.modules.auth.services`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.modules.auth.permissions import Role


class User(db.Model):  # type: ignore[name-defined]
    """A registered user of any of the six roles.

    ``password_hash`` is the only credential stored. It is written via
    :meth:`set_password` (Werkzeug scrypt) and never serialised.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            name="user_role",
            # Store the enum *values* (snake_case), not the member names.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )
    #: Set for Event Organisers only (SCRUM-66 AC2, ADR-0013). A database-level foreign
    #: key only: the organisations module's model is not imported (module boundary).
    organisation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("client_organisations.id"), index=True, nullable=True
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

    # -- credentials -----------------------------------------------------

    def set_password(self, password: str) -> None:
        """Hash ``password`` and store the hash. Plaintext is never kept."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Return ``True`` if ``password`` matches the stored hash."""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        role = getattr(self.role, "value", self.role)
        return f"<User id={self.id} email={self.email!r} role={role!r}>"
