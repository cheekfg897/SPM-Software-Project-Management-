"""Unit tests for how the app finds its database (SCRUM-5).

CI and docker-compose set ``DATABASE_URL``, and a laptop usually has only the
``POSTGRES_*`` variables, so whichever isn't set here is a path the suite never ran. The
tests set the environment themselves, so both run wherever the suite does.
"""

from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from app.config import _build_database_uri

pytestmark = pytest.mark.scrum_5

DATABASE_VARIABLES = (
    "DATABASE_URL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
)


@pytest.fixture(autouse=True)
def no_database_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test with none of them set, whatever this machine's are."""
    for variable in DATABASE_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def _set_every_postgres_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_USER", "gwen")
    monkeypatch.setenv("POSTGRES_PASSWORD", "harbour")
    monkeypatch.setenv("POSTGRES_HOST", "db.example.test")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_DB", "planning")


def test_database_url_wins_over_the_postgres_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_every_postgres_variable(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///named-by-the-environment.db")

    assert _build_database_uri() == "sqlite:///named-by-the-environment.db"


def test_each_postgres_variable_fills_its_own_part(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_every_postgres_variable(monkeypatch)

    url = make_url(_build_database_uri())

    assert url.drivername == "postgresql+psycopg2"
    assert url.username == "gwen"
    assert url.password == "harbour"
    assert url.host == "db.example.test"
    assert url.port == 6543
    assert url.database == "planning"


def test_an_empty_database_url_counts_as_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_every_postgres_variable(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "")

    assert make_url(_build_database_uri()).database == "planning"


def test_with_nothing_set_it_falls_back_to_the_local_database() -> None:
    url = make_url(_build_database_uri())

    assert url.username == "connectsphere"
    assert url.password == "connectsphere"
    assert url.host == "localhost"
    assert url.port == 5432
    assert url.database == "connectsphere"
