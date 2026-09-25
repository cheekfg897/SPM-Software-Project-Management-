# ConnectSphere — Event Planning and Venue Booking System

Backend for ConnectSphere's event planning and venue booking platform (IS212 scrum project), built as a **modularised monolith**: one Flask app, internally split into self-contained modules that only talk through service functions.

User stories and their acceptance criteria live in Jira (project **SCRUM**), the single source of truth for requirements. Decisions made where a story is silent are recorded in [docs/adr/](docs/adr/README.md).

## Repository layout

```
backend/            Flask application (see below)
  app/
    __init__.py     app factory: create_app()
    config.py       Dev / Test / Prod config, loaded from environment
    extensions.py   db, migrate, jwt instances
    common/         cross-cutting: error handlers, requires_auth / requires_role
    modules/auth/   models, routes, schemas, services, permissions
    modules/events/ event requests (SCRUM-19), event status model (SCRUM-22), filed under the organiser's organisation (SCRUM-66)
    modules/organisations/ client organisations that Event Organisers belong to (SCRUM-66)
    modules/venue/  venue catalogue (SCRUM-25), availability calendar (SCRUM-26), search (SCRUM-35), setup/turnaround (SCRUM-67)
  tests/            unit tests (pytest), one marker per story
  migrations/       Alembic migrations (Flask-Migrate)
docs/adr/           Architecture Decision Records: choices made where requirements were silent
backend/CONVENTIONS.md   Python conventions: style, naming, typing, testing
docs/code-review-checklist.md   what to check when reviewing a PR
CLAUDE.md           working rules for Claude Code (commands, architecture rules, gotchas)
frontend/           placeholder only — framework not yet decided
docker-compose.yml  Postgres + backend for local development
.github/workflows/  CI: migrate against Postgres, run unit tests
```

## Prerequisites

- Python 3.12+
- Docker Desktop (for PostgreSQL). Alternatively a local PostgreSQL 14+ server.
- Git

## 1. Configure environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` if you want different credentials. The same file is read by the `postgres` container and by the Flask app, so it only needs to be set in one place. Never commit `backend/.env`.

## 2. Start PostgreSQL

```bash
docker compose up -d postgres
```

Wait until `docker compose ps` shows the `postgres` service as `healthy`.

## 3. Run the backend locally

```bash
cd backend
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# Apply migrations (creates the users table)
flask db upgrade

# Start the API on http://localhost:5000
flask run
```

`FLASK_APP=wsgi` is set in `.env`, so `flask` finds the app automatically.

### Alternative: run everything in Docker

```bash
docker compose up
```

This starts Postgres, installs dependencies in a `python:3.12-slim` container, runs `flask db upgrade`, and serves the API on port 5000.

## 4. Try the API

```bash
# Register
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"Password123","full_name":"Alice","role":"venue_staff"}'

# Log in → returns access_token
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"Password123"}'

# Authenticated routes
curl http://localhost:5000/api/auth/me            -H "Authorization: Bearer <token>"
curl http://localhost:5000/api/auth/internal-only -H "Authorization: Bearer <token>"
```

| Route                          | Access                                                          |
| ------------------------------ | --------------------------------------------------------------- |
| `POST /api/auth/register`      | public                                                          |
| `POST /api/auth/login`         | public                                                          |
| `GET  /api/auth/me`            | any authenticated user                                          |
| `GET  /api/auth/internal-only` | `event_coordinator`, `venue_staff`, `technical_support_staff`   |
| `POST /api/events/requests`    | `event_organiser` — submit an event request                     |
| `GET  /api/events/requests`    | `event_organiser` — list your own event requests                |
| `GET  /api/events/requests/<reference>` | `event_organiser` — one of your own event requests, with its current status (`404` if it isn't yours) |
| `POST /api/organisations`      | internal roles — record a client organisation                   |
| `GET  /api/organisations`      | internal roles — list client organisations, by name             |
| `POST /api/venues`             | `venue_staff` — add a venue                                     |
| `GET  /api/venues`             | any authenticated user — list active venues, by name            |
| `GET  /api/venues/<id>`        | any authenticated user — one venue, active or not               |
| `PATCH /api/venues/<id>`       | `venue_staff` — change only the fields sent; lists confirmed bookings that newly overlap if setup/turnaround changed |
| `POST /api/venues/<id>/deactivate` | `venue_staff` — hide from listing and search            |
| `POST /api/venues/<id>/reactivate` | `venue_staff` — show again                              |
| `GET  /api/venues/<id>/calendar?range_start=…&range_end=…` | internal roles — bookings and blocked periods in the range |
| `POST /api/venues/search`      | `event_coordinator` — venues that meet an event's requirements and are free |

Roles: `event_organiser`, `attendee`, `event_coordinator`, `venue_staff`, `technical_support_staff`.

Password policy: at least 8 characters, with at least one letter and one digit.

An `event_organiser` registers with the `organisation_id` of an existing client organisation, which an internal user records first; every other role must leave it out ([ADR-0013](docs/adr/0013-client-organisations-recorded-by-internal-users.md)).

All errors share one shape: `{"error": "<code>", "message": "<text>", "details": {...}}` (`details` only for validation errors).

Date-times (bookings, blocks, calendar ranges) should carry an offset, such as `Z` or `+08:00`. One sent without an offset is read as business time (`APP_TIMEZONE`, Singapore by default). They're stored in UTC and come back in business time, e.g. `2026-10-01T17:00:00+08:00` ([ADR-0009](docs/adr/0009-booking-times-in-utc.md)).

## 5. Run the tests

The suite is unit tests only, and **Postgres does not need to be running**. Most tests mock the database; the venue service tests run against an in-memory SQLite database, so their queries really execute.

```bash
cd backend
pytest --cov=app --cov-report=term-missing
```

Run a single story's tests via its marker:

```bash
pytest -m scrum_65   # create an account
pytest -m scrum_6    # log in
pytest -m scrum_21   # enforce permissions
pytest -m scrum_19   # submit an event request
pytest -m scrum_22   # event status model
pytest -m scrum_25   # update venue catalogue
pytest -m scrum_26   # view a venue's availability calendar
pytest -m scrum_35   # search and filter venues
pytest -m scrum_67   # setup and turnaround time
pytest -m scrum_66   # client organisations
```

## Database migrations

```bash
cd backend
flask db upgrade                 # apply
flask db migrate -m "message"    # autogenerate after changing a model
flask db check                   # fail if models and migrations have drifted
flask db downgrade               # roll back one revision
```

## Architecture note (modularised monolith)

- One deployable Flask app; each bounded context lives in `backend/app/modules/<name>/` with its own models, routes, schemas, services and permissions.
- Modules expose a `register(app)` hook and talk to each other **only** through functions in their `services.py`. No module imports another module's models.
- `app/common/` holds cross-cutting mechanisms (error shape, `requires_auth`, `requires_role`) and never imports from `app/modules/`.
- Trade-off: simplicity now (one repo, one deploy, one DB, no network boundaries) versus the option to split modules into services later without a rewrite, because the seams already exist.
