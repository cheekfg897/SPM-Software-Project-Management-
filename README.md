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
    modules/events/ event requests (SCRUM-19), event status model (SCRUM-22), filed under the organiser's organisation (SCRUM-66) and seen by its organisers (SCRUM-7), coordinator assignment and event history (SCRUM-30), equipment lines (SCRUM-37), equipment awaiting Technical Support (SCRUM-38), save and resume a draft (SCRUM-20), editing an event and its history (SCRUM-33), each role's event lists and the coordinator's event record (SCRUM-24)
    modules/organisations/ client organisations that Event Organisers belong to (SCRUM-66)
    modules/notifications/ in-app notifications about events (SCRUM-28)
    modules/venue/  venue catalogue (SCRUM-25), availability calendar (SCRUM-26), search (SCRUM-35), suitability check (SCRUM-36), setup/turnaround (SCRUM-67), blocks (SCRUM-34)
    modules/equipment/ equipment catalogue (SCRUM-27)
  tests/            unit tests (pytest), one marker per story
  migrations/       Alembic migrations (Flask-Migrate)
docs/adr/           Architecture Decision Records: choices made where requirements were silent
backend/CONVENTIONS.md   Python conventions: style, naming, typing, testing
docs/code-review-checklist.md   what to check when reviewing a PR
CLAUDE.md           working rules for Claude Code (commands, architecture rules, gotchas)
frontend/           React + TypeScript web app (see frontend/README.md)
docker-compose.yml  Postgres + backend for local development
.github/workflows/  CI on every PR and push to main: lint, migrations, unit tests, coverage comment; PR title check
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

`event_coordinator`, `venue_staff` and `technical_support_staff` accounts aren't
self-registered; an operator creates one with the CLI command instead
([ADR-0023](docs/adr/0023-staff-accounts-created-by-command.md)):

```bash
flask create-staff-user --email alice@example.com --full-name Alice --role venue_staff
# Password:                  (type it; nothing is shown)
# Repeat for confirmation:   (type it again)
# Created venue_staff account for alice@example.com (id 1).

# Or, running in Docker (see the Docker alternative above):
docker compose exec backend flask create-staff-user --email alice@example.com --full-name Alice --role venue_staff
```

```bash
# Register (public; only event_organiser or attendee — staff comes from the command above)
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"bob@example.com","password":"Password123","full_name":"Bob","role":"attendee"}'

# Log in as the staff account created above → returns access_token
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"Password123"}'

# Authenticated routes
curl http://localhost:5000/api/auth/me            -H "Authorization: Bearer <token>"
curl http://localhost:5000/api/auth/internal-only -H "Authorization: Bearer <token>"
```

| Route                          | Access                                                          |
| ------------------------------ | --------------------------------------------------------------- |
| `POST /api/auth/register`      | public — `event_organiser` or `attendee` only; staff accounts come from `flask create-staff-user` ([ADR-0023](docs/adr/0023-staff-accounts-created-by-command.md)) |
| `POST /api/auth/login`         | public                                                          |
| `GET  /api/auth/me`            | any authenticated user                                          |
| `GET  /api/auth/internal-only` | `event_coordinator`, `venue_staff`, `technical_support_staff`   |
| `POST /api/events/requests`    | `event_organiser` — submit an event request                     |
| `GET  /api/events/requests`    | `event_organiser` — list your client organisation's event requests and your own drafts, whoever submitted them, newest first; a colleague's drafts are hidden (`403` if your account has no organisation); an empty list comes with a `message` |
| `POST /api/events/requests/drafts` | `event_organiser` — save a draft with only the event name required; every other field is optional and checked on its own |
| `PATCH /api/events/requests/drafts/<reference>` | `event_organiser` — on one of your own drafts, change only the fields sent; a field sent as `null` clears it, `name` cannot be (`404` if it isn't yours or doesn't exist; `409` if it is no longer a draft) |
| `POST /api/events/requests/drafts/<reference>/submit` | `event_organiser` — submit one of your own drafts under the full submission rules, keeping its reference; assigned and notified exactly as a fresh submission is (`400` if a detail is missing or fails a rule) |
| `GET  /api/events/requests/assigned` | `event_coordinator` — the event requests assigned to you, newest first; an empty list comes with a `message` |
| `GET  /api/events/requests/with-equipment` | `technical_support_staff` — every event that has an equipment request, whatever its status or date: name, date, times and status; an empty list comes with a `message` |
| `GET  /api/events/requests/awaiting-equipment` | `technical_support_staff` — every upcoming event with equipment lines still `requested`: the event's name, date and times, those lines, and the days remaining; soonest first |
| `GET  /api/events/requests/<reference>` | `event_organiser` — one of your client organisation's event requests and your own drafts, with its current status, the assigned coordinator's name and email (`null` until assigned) and its equipment lines (`404` if it is another organisation's or a colleague's draft; `403` if your account has no organisation). `event_coordinator` — the same, for a request assigned to you; otherwise `404` |
| `POST /api/events/requests/<reference>/equipment` | `event_coordinator` — add an equipment line (type, quantity, notes) to a request assigned to you, while it is awaiting review; notifies Technical Support Staff (`404` if it isn't assigned to you) |
| `GET  /api/events/requests/<reference>/equipment` | `event_coordinator` (requests assigned to you), `technical_support_staff` (any request but a draft) — the event's date and times (`event`, so Technical Support know by when) and its equipment lines with their status |
| `PATCH /api/events/requests/<reference>/equipment/<line_id>` | `event_coordinator` — on a request assigned to you, change only the fields sent, while it is awaiting review |
| `DELETE /api/events/requests/<reference>/equipment/<line_id>` | `event_coordinator` — on a request assigned to you, remove a line, while it is awaiting review |
| `POST /api/events/requests/<reference>/reassign` | `event_coordinator` — on a request assigned to you, move it while submitted, under review or confirmed to the Event Coordinator named by `coordinator_email`; recorded in its history and the new coordinator is notified. Returns the request and the new coordinator's name and email |
| `PATCH /api/events/requests/<reference>` | `event_coordinator` — on a request assigned to you, while it is submitted, under review or confirmed, change only the fields sent (notes, dates, times, attendance, venue/equipment requirements); a value equal to what's saved is not a change. Returns the request, its programme and internal planning notes, and the list of changes made, each flagged `significant` if it could affect a venue booking or requested equipment. A significant change that could affect equipment already requested notifies Technical Support Staff |
| `GET  /api/events/requests/<reference>/history` | internal roles (any event but a draft), `event_organiser` (your own client organisation's) — the event's history oldest first: coordinator assignment and reassignment, and each field edited, with who did it and when, names resolved and no user ids. An organiser never sees an internal planning notes change |
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
| `POST /api/venues/<id>/blocks` | `venue_staff` — block a period with a reason; lists the confirmed bookings it cuts into |
| `GET  /api/venues/<id>/blocks` | `venue_staff` — the venue's blocks with ids and reasons, in start order |
| `DELETE /api/venues/<id>/blocks/<block_id>` | `venue_staff` — remove a block; the venue is available again |
| `POST /api/venues/<id>/suitability` | `event_coordinator`, `venue_staff` — whether the venue meets an event's requirements, with each reason it doesn't |
| `POST /api/equipment/types`    | `technical_support_staff` — add an equipment type               |
| `GET  /api/equipment/types`    | internal roles — every equipment type with its total quantity, by name |
| `GET  /api/equipment/types/<id>` | internal roles — one equipment type                           |
| `PATCH /api/equipment/types/<id>` | `technical_support_staff` — change only the fields sent; sending `venue_id` or `store_name` replaces the location |
| `GET  /api/notifications`      | any authenticated user — your notifications, newest first      |
| `GET  /api/notifications/unread-count` | any authenticated user — how many of yours are unread   |
| `POST /api/notifications/<id>/read` | any authenticated user — mark one of yours read (`404` if it isn't yours) |

Roles: `event_organiser`, `attendee`, `event_coordinator`, `venue_staff`, `technical_support_staff`.

Password policy: at least 8 characters, with at least one letter and one digit.

An `event_organiser` registers with the `organisation_id` of an existing client organisation, which an internal user records first; an attendee must leave it out ([ADR-0013](docs/adr/0013-client-organisations-recorded-by-internal-users.md)). Every organiser of an organisation sees all of its event requests, and no other organisation's ([ADR-0020](docs/adr/0020-organisers-see-their-organisations-events.md)).

A draft is an event request in status `draft`: it can be saved with only a name, reopened and changed field by field, and submitted in place once it is complete, keeping its reference. It is visible only to the organiser who saved it — never to a colleague, and never to Event Coordinators or Technical Support Staff — until it is submitted ([ADR-0024](docs/adr/0024-draft-event-requests.md)).

A submitted event request is assigned to the Event Coordinator with the fewest open requests (`submitted` or `under_review`), lowest user id on a tie, and only that coordinator is notified; with no Event Coordinator registered it stays unassigned and nobody is notified ([ADR-0018](docs/adr/0018-least-loaded-coordinator-and-event-history.md)). Everything that happens to an event is written to an event history table that later stories append to.

All errors share one shape: `{"error": "<code>", "message": "<text>", "details": {...}}` (`details` only for validation errors).

An equipment type is kept at exactly one place: a catalogued venue (`venue_id`) or a named store (`store_name`). Equipment type names are unique ([ADR-0014](docs/adr/0014-equipment-type-location-and-quantity.md)).

An event has at most one equipment line per equipment type (edit the line to change the quantity), and its lines can be added, changed or removed only by the request's assigned coordinator and only while the request is `submitted` or `under_review` ([ADR-0019](docs/adr/0019-event-equipment-lines.md)).

Technical Support Staff share one list of the equipment awaiting them: an event is on it while any of its lines is still `requested`, its date is today or later, and it isn't completed, cancelled or rejected ([ADR-0022](docs/adr/0022-equipment-awaiting-action.md)).

An event's assigned coordinator can edit its notes, dates, times, attendance and requirements text while it is `submitted`, `under_review` or `confirmed`; a value equal to what's already saved is not a change. Every changed field is written to the event's history, flagged `significant` if it could affect a venue booking or the equipment already requested; a significant change that could affect equipment notifies every Technical Support Staff member once per edit, but only if the event already has an equipment line to reassess ([ADR-0025](docs/adr/0025-event-edits-significant-changes-and-history.md)).

Date-times (bookings, blocks, calendar ranges) should carry an offset, such as `Z` or `+08:00`. One sent without an offset is read as business time (`APP_TIMEZONE`, Singapore by default). They're stored in UTC and come back in business time, e.g. `2026-10-01T17:00:00+08:00` ([ADR-0009](docs/adr/0009-booking-times-in-utc.md)). Notification times (`created_at`, `read_at`) come back the same way.

## 5. Run the tests

The suite is unit tests only, and **Postgres does not need to be running**. Most tests mock the database; the venue, equipment, notifications, coordinator-assignment and event equipment service tests run against an in-memory SQLite database, so their queries really execute.

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
pytest -m scrum_20   # save and resume a draft event request
pytest -m scrum_22   # event status model
pytest -m scrum_24   # see the events my role is involved in
pytest -m scrum_25   # update venue catalogue
pytest -m scrum_26   # view a venue's availability calendar
pytest -m scrum_27   # maintain the equipment catalogue
pytest -m scrum_28   # receive notifications about my events
pytest -m scrum_30   # assign a coordinator to a submitted event
pytest -m scrum_34   # block a venue
pytest -m scrum_35   # search and filter venues
pytest -m scrum_36   # check whether a venue suits an event
pytest -m scrum_37   # record what equipment an event needs
pytest -m scrum_38   # see the equipment requests awaiting my action
pytest -m scrum_67   # setup and turnaround time
pytest -m scrum_66   # client organisations
pytest -m scrum_7    # see only my own organisation's events
pytest -m scrum_87   # reassign an event to a different coordinator
pytest -m scrum_88   # staff accounts come from a command, not self-registration
pytest -m scrum_33   # update event information and flag significant changes
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
