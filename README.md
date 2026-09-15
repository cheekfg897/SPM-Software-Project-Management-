# ConnectSphere — Event Planning and Venue Booking System

Backend for ConnectSphere's event planning and venue booking platform (IS212 scrum project), built as a **modularised monolith**: one Flask app, internally split into self-contained modules that only talk through service functions.

Sprint 1 scope: the auth foundation — account creation, login, and role-based permission enforcement. Sprint 2 scope: venue management — catalogue CRUD, availability calendar, search, and setup/turnaround buffer times. See [backend/STORIES.md](backend/STORIES.md) for the user stories and acceptance criteria.

## Repository layout

```
backend/            Flask application (see below)
  app/
    __init__.py     app factory: create_app()
    config.py       Dev / Test / Prod config, loaded from environment
    extensions.py   db, migrate, jwt instances
    common/         cross-cutting: error handlers, requires_auth / requires_role
    modules/auth/   models, routes, schemas, services, permissions
    modules/venue/  models, routes, schemas, services (venue catalogue, calendar, search)
  tests/            unit tests (pytest), one marker per story
  migrations/       Alembic migrations (Flask-Migrate)
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
| `POST   /api/venues`                    | `venue_staff`                                                  |
| `GET    /api/venues`                    | any authenticated user                                         |
| `GET    /api/venues/<id>`               | any authenticated user                                         |
| `PATCH  /api/venues/<id>`               | `venue_staff`                                                  |
| `POST   /api/venues/<id>/deactivate`    | `venue_staff`                                                  |
| `POST   /api/venues/<id>/reactivate`    | `venue_staff`                                                  |
| `POST   /api/venues/<id>/blocks`        | `venue_staff`                                                  |
| `GET    /api/venues/<id>/calendar`      | `event_coordinator`, `venue_staff`, `technical_support_staff`  |
| `POST   /api/venues/search`             | any authenticated user                                         |

Roles: `event_organiser`, `attendee`, `event_coordinator`, `venue_staff`, `technical_support_staff`.

Password policy: at least 8 characters, with at least one letter and one digit.

All errors share one shape: `{"error": "<code>", "message": "<text>", "details": {...}}` (`details` only for validation errors).

## 5. Run the tests

The test suite (Sprint 1 + Sprint 2) is unit tests only. The database is mocked, so **Postgres does not need to be running**.

```bash
cd backend
pytest --cov=app --cov-report=term-missing
```

Run a single story's tests via its marker:

```bash
pytest -m story_create_account
pytest -m story_login
pytest -m story_permissions
pytest -m story_venue_catalogue
pytest -m story_venue_calendar
pytest -m story_venue_search
pytest -m story_venue_setup_turnaround
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
