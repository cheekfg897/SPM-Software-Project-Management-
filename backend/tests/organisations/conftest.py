"""Fixtures shared by the organisations tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.modules.organisations.models import ClientOrganisation


@pytest.fixture()
def make_organisation() -> Callable[..., ClientOrganisation]:
    """Factory for in-memory ``ClientOrganisation`` objects (never persisted)."""
    counter = {"id": 0}

    def _make(
        *,
        name: str = "Acme Events",
        contact_name: str = "Alice Tan",
        contact_email: str = "alice@acme.example",
        contact_phone: str | None = None,
    ) -> ClientOrganisation:
        counter["id"] += 1
        organisation = ClientOrganisation(
            name=name,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
        )
        organisation.id = counter["id"]
        return organisation

    return _make
