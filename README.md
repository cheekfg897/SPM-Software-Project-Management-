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
    common/         cross-cutting: error handlers, requires_auth / requires_role / optional_auth
    modules/auth/   models, routes, schemas, services, permissions
    modules/events/ event requests (SCRUM-19), event status model (SCRUM-22), filed under the organiser's organisation (SCRUM-66) and seen by its organisers (SCRUM-7), coordinator assignment and event history (SCRUM-30), equipment lines (SCRUM-37), equipment awaiting Technical Support (SCRUM-38), save and resume a draft (SCRUM-20), editing an event and its history (SCRUM-33), each role's event lists and the coordinator's event record (SCRUM-24), reviewing and deciding a request (SCRUM-31), asking the organiser for clarification (SCRUM-32)
    modules/organisations/ client organisations that Event Organisers belong to (SCRUM-66)
    modules/notifications/ in-app notifications about events (SCRUM-28), with an optional detail such as a decision's reason (SCRUM-31) or a clarification's question or answer (SCRUM-32)
    modules/venue/  venue catalogue (SCRUM-25), availability calendar (SCRUM-26), search (SCRUM-35), suitability check (SCRUM-36), setup/turnaround (SCRUM-67), blocks (SCRUM-34)
    modules/equipment/ equipment catalogue (SCRUM-27), availability and reservations (SCRUM-45, SCRUM-46), taking damaged equipment out of circulation (SCRUM-47)
    modules/registration/ the event catalogue, registering for a confirmed event, an attendee's own registrations (SCRUM-52), withdrawing (SCRUM-53) and who has registered for an event (SCRUM-55)
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

`event_coordinator`, `event_coordinator_lead`, `venue_staff`, `technical_support_staff` and
`safety_officer` accounts aren't
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

Tentative venue holds expire on a clock. `flask expire-holds` marks the holds whose expiry
has passed Expired and warns coordinators 24 hours before; running it again repeats
nothing. The scheduled *Expire Tentative Holds* workflow runs it every hour once a
`DATABASE_URL` repository secret exists, and skips until then
([ADR-0052](docs/adr/0052-expire-tentative-holds.md)):

```bash
flask expire-holds
# Expired 1 hold(s); warned about 0 hold(s).
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

# Log out: the token is refused from then on (204)
curl -X POST http://localhost:5000/api/auth/logout -H "Authorization: Bearer <token>"
```

| Route                          | Access                                                          |
| ------------------------------ | --------------------------------------------------------------- |
| `POST /api/auth/register`      | public — `event_organiser` or `attendee` only; staff accounts come from `flask create-staff-user` ([ADR-0023](docs/adr/0023-staff-accounts-created-by-command.md)) |
| `POST /api/auth/login`         | public                                                          |
| `POST /api/auth/logout`        | any authenticated user — revokes the token sent, which gets `401` from then on; the user's other sessions carry on (`204`, [ADR-0110](docs/adr/0110-logout-revokes-the-access-token.md)) |
| `GET  /api/auth/me`            | any authenticated user                                          |
| `GET  /api/auth/internal-only` | `event_coordinator`, `event_coordinator_lead`, `venue_staff`, `technical_support_staff`, `safety_officer` |
| `POST /api/events/requests`    | `event_organiser` — submit an event request                     |
| `GET  /api/events/requests`    | `event_organiser` — list your client organisation's event requests and your own drafts, whoever submitted them, newest first; a colleague's drafts are hidden (`403` if your account has no organisation); an empty list comes with a `message` |
| `POST /api/events/requests/drafts` | `event_organiser` — save a draft with only the event name required; every other field is optional and checked on its own |
| `PATCH /api/events/requests/drafts/<reference>` | `event_organiser` — on one of your own drafts, change only the fields sent; a field sent as `null` clears it, `name` cannot be (`404` if it isn't yours or doesn't exist; `409` if it is no longer a draft) |
| `POST /api/events/requests/drafts/<reference>/submit` | `event_organiser` — submit one of your own drafts under the full submission rules, keeping its reference; it waits in the Lead's queue and tells the Leads exactly as a fresh submission does (`400` if a detail is missing or fails a rule) |
| `GET  /api/events/requests/assigned` | `event_coordinator` — the event requests assigned to you, newest first; an empty list comes with a `message` |
| `GET  /api/events/requests/unassigned` | `event_coordinator_lead` — the Lead's queue of submitted requests no coordinator has yet: each one's reference, name, date, times, expected attendance, submission time and status, longest-waiting first; an empty list comes with a `message`. Every other role, Event Coordinators included, gets `403` |
| `GET  /api/events/requests/with-venue-bookings` | `venue_staff` — every event that has a venue booking request or a booking, whatever its status (drafts aside) or date: name, date, times and status, the same list for all Venue Staff; an event whose only requests were withdrawn, released or cancelled is left out ([ADR-0085](docs/adr/0085-venue-staff-event-list.md)); an empty list comes with a `message`. Every other role gets `403` |
| `GET  /api/events/requests/with-equipment` | `technical_support_staff` — every event that has an equipment request, whatever its status or date: name, date, times and status; an empty list comes with a `message` |
| `GET  /api/events/requests/awaiting-safety-review` | `safety_officer` — every event in Safety Review, soonest first: its name, date, times, status, expected attendance and accessibility needs, each booked venue's capacity, layouts, facilities, accessibility features and period, and each equipment request with its quantity, notes and Technical Support's outcome ([ADR-0047](docs/adr/0047-safety-officer-and-safety-review.md)); an empty list comes with a `message`. Every other role gets `403` |
| `POST /api/events/requests/<reference>/safety-outcome` | `safety_officer` — record `approved`, `rejected` or `changes_requested` for an event in Safety Review, with a note on each of the seven `checklist` items, and a `reason` unless approving. Approve keeps the event in Safety Review, approved; Reject and Request Changes return it to `approved` (planning). The assigned coordinator is notified. With Reject or Request Changes, `flagged_arrangement_ids` and `reopened_line_ids` name what to rework: each arrangement is flagged for Venue Staff to reconfirm and each line reopened for Technical Support, who are told ([ADR-0113](docs/adr/0113-safety-officer-names-what-to-rework.md)). `409 safety_outcome_not_allowed` if the event isn't in Safety Review or is already approved ([ADR-0047](docs/adr/0047-safety-officer-and-safety-review.md)). Every other role gets `403` |
| `GET  /api/events/requests/awaiting-equipment` | `technical_support_staff` — every upcoming event with equipment lines still `requested`, or whose reservation awaits reassessment (with no line to show when the event has no line of that type): the event's name, date and times, those lines, the days remaining and `equipment_type_ids_to_reassess` ([ADR-0114](docs/adr/0114-reassess-equipment-reservations-after-a-change.md)); soonest first |
| `GET  /api/events/requests/active` | `event_coordinator_lead` — every active event (one with a coordinator, in Submitted, Under Review, Awaiting Clarification, Approved, Safety Review or Confirmed) with its coordinator's name and status; newest first. A submitted request nobody holds yet is only in the queue ([ADR-0120](docs/adr/0120-lead-oversight-active-events-and-every-coordinator.md)) |
| `GET  /api/events/coordinators/workload` | `event_coordinator_lead` — every Event Coordinator by name, with `active_count` and their active events, newest first; one who holds none is listed with `0`, so the Lead can see who is free. The list comes with a `message` only when there is no Event Coordinator ([ADR-0120](docs/adr/0120-lead-oversight-active-events-and-every-coordinator.md)) |
| `GET  /api/events/requests/<reference>` | `event_organiser` — one of your client organisation's event requests and your own drafts, with its current status, the assigned coordinator's name and email (`null` until assigned), its current `decision` (outcome, reason, the coordinator's name and when; `null` until decided) and its `clarifications` (each question with who asked and when, and the answer with who answered and when; the answer `null` while outstanding), and everything else on the record at every stage: the planning notes, every venue arrangement in full (status, hold expiry, flags with their reasons, Venue Staff's reason, the venue's capacity, facilities and accessibility features, preparation), each equipment line with its notes, outcome, shortfall and reviewer, the reservations with their preparation, and the current safety check with its checklist ([ADR-0104](docs/adr/0104-organiser-sees-everything-on-the-record.md)), and its `change_requests`, oldest first, which the assigned coordinator sees too ([ADR-0126](docs/adr/0126-request-a-change-after-submitting.md)) (`404` if it is another organisation's or a colleague's draft; `403` if your account has no organisation). `event_coordinator` — for a request assigned to you, the request, its coordinator, decision, clarifications, equipment lines and every venue arrangement in full (SCRUM-93 AC5, [ADR-0105](docs/adr/0105-reviewer-and-every-arrangement-on-the-staff-record.md)); otherwise `404` |
| `POST /api/events/requests/<reference>/equipment` | `event_coordinator` — add an equipment line (type, quantity, notes) to a request assigned to you, until the event is confirmed (ADR-0092); records a significant change in the event history and notifies Technical Support Staff (`404` if it isn't assigned to you) |
| `GET  /api/events/requests/<reference>/equipment` | `event_coordinator` (requests assigned to you), `technical_support_staff` (any request but a draft) — the event's date and times (`event`, so Technical Support know by when) and its equipment lines with their status and review outcome (provided quantity, shortfall, note, reviewer, time) |
| `PATCH /api/events/requests/<reference>/equipment/<line_id>` | `event_coordinator` — on a request assigned to you, change only the fields sent, until the event is confirmed; a new type or quantity is a significant change in the history that clears the line's outcome and notifies Technical Support Staff, and a new type releases the old type's reservations (ADR-0092) |
| `DELETE /api/events/requests/<reference>/equipment/<line_id>` | `event_coordinator` — on a request assigned to you, remove a line, until the event is confirmed; a significant change in the history that releases the event's reservations of that type and notifies Technical Support Staff (ADR-0092) |
| `POST /api/events/requests/<reference>/equipment/<line_id>/outcome` | `technical_support_staff` — record or revise the review outcome; a note is required unless the whole request is met; the coordinator is notified. The line's reservations awaiting reassessment keep what it provides for the event's period and release the rest; keeping more than is free is `409 reservation_cannot_move` (ADR-0114) |
| `POST /api/events/requests/<reference>/reassign` | `event_coordinator_lead` — move any request while submitted, under review, awaiting clarification, approved, in safety review or confirmed to the Event Coordinator named by `coordinator_email`; recorded in its history, and the new coordinator, the previous coordinator and the organiser are notified. Returns the request and the new coordinator's name and email |
| `POST /api/events/requests/<reference>/coordinator` | `event_coordinator_lead` — give a request in the queue to the Event Coordinator named by `coordinator_email`; recorded in its history with the Lead as the actor, and the coordinator and the organiser are notified. A request that already has a coordinator, or isn't `submitted`, is `409`; the request is read under a row lock, so when two Leads assign it at once the first is kept and the second gets that `409` ([ADR-0120](docs/adr/0120-lead-oversight-active-events-and-every-coordinator.md)). Returns the request and the coordinator's name and email. Every other role gets `403` |
| `POST /api/events/requests/<reference>/complete` | `event_coordinator` — on a request assigned to you, mark it completed once it is confirmed and its end date and time have passed (business time); recorded in its history with who did it and when. `409` if it isn't confirmed or hasn't ended yet. Returns the request |
| `PATCH /api/events/requests/<reference>` | `event_coordinator` — on a request assigned to you, while it is submitted, under review, awaiting clarification, approved or in Safety Review (a confirmed event is `409`: it changes only through a change request, ADR-0101), change only the fields sent (notes, dates, times, attendance, venue/equipment requirements); a value equal to what's saved is not a change. Returns the request, its programme and internal planning notes, and the list of changes made, each flagged `significant` if it could affect a venue booking or requested equipment. A significant change that could affect equipment already requested notifies Technical Support Staff; a date or time change marks every equipment reservation for reassessment and reopens lines recorded unavailable or partially fulfilled (ADR-0114) |
| `GET  /api/events/requests/<reference>/history` | `event_coordinator` (requests assigned to you), the Lead, Venue Staff and Technical Support (any event but a draft), `event_organiser` (your own client organisation's) — the event's history oldest first: coordinator assignment and reassignment, each field edited, the start of its review, every clarification question and answer, every decision and completion, with who did it and when, names resolved and no user ids. The organiser reads every entry, as staff do (ADR-0104) |
| `GET  /api/events/requests/<reference>/staff-record` | `venue_staff`, `technical_support_staff`, `safety_officer`, `event_coordinator_lead` — any event but a draft, assigned or not, read-only: the request with its programme and internal planning notes, its coordinator, decision and clarifications, every venue arrangement in any status, in full (venue and location, period, what was asked for, status, Venue Staff's reason, hold expiry, flags, preparation), its equipment requests by name with Technical Support's outcome and who reviewed them, its reservations with their preparation, and the outcome of its current safety check (`null` until there is one); no ids and no registrants ([ADR-0095](docs/adr/0095-read-only-event-record-for-internal-staff.md)). Every other role, an Event Coordinator included, gets `403`; a draft is `404` |
| `POST /api/events/requests/<reference>/safety-review` | `event_coordinator` — on an approved request assigned to you, send it to Safety Review once it has a venue, every active venue arrangement is approved and every equipment request has an outcome from Technical Support (no equipment is fine); recorded in its history, and every Safety Officer is notified. `409 safety_review_not_allowed` otherwise, with `details` naming each unapproved arrangement and each request without an outcome ([ADR-0047](docs/adr/0047-safety-officer-and-safety-review.md)). Returns the request |
| `POST /api/events/requests/<reference>/confirm` | `event_coordinator` — on a request in Safety Review assigned to you, confirm the event once the Safety Officer has approved it, it has a venue, every active venue arrangement is approved and every equipment request has an outcome (no equipment is fine); recorded in its history, and the organiser who submitted it is notified. `409 confirmation_not_allowed` otherwise, with `details` naming the safety check, each unapproved arrangement and each request without an outcome ([ADR-0051](docs/adr/0051-confirm-an-event.md)). Returns the request |
| `POST /api/events/requests/<reference>/reject` | `event_coordinator` — on a request assigned to you that is approved or in Safety Review, reject the event because an essential arrangement can't be met, with a `reason` (`400` without one). Recorded in its history as a `rejected` decision with the reason, so it is the current decision, and the submitting organiser is notified with the reason. In the same commit its pending, conflicting, rejected or expired venue arrangements are withdrawn, its approved or held ones are released with their bookings and holds cancelled, and its equipment reservations are returned; its open equipment requests are closed. `409 rejection_not_allowed` in any other status ([ADR-0093](docs/adr/0093-reject-an-event-during-planning.md)). Returns the request |
| `POST /api/events/requests/<reference>/review` | `event_coordinator` — on a request assigned to you, move it from submitted to under review; recorded in its history, nobody is notified (`409` for any other status) |
| `POST /api/events/requests/<reference>/decide` | `event_coordinator` — on a request assigned to you, record `{"outcome": "approved" \| "rejected", "reason"}` while it is submitted, under review or awaiting clarification, or change an approved or rejected one's decision; a rejection or a change needs a reason. Recorded in its history, and the submitting organiser is notified with the reason (`409` for an approval while a clarification request is outstanding, for a change of decision once the event has an equipment request, or when it is confirmed, completed or cancelled) |
| `POST /api/events/requests/<reference>/request-clarification` | `event_coordinator` — on a request assigned to you and under review, ask the organiser `{"message"}`; the request becomes awaiting clarification, the question is recorded in its history, and the submitting organiser is notified with it (`409` for any other status, including a question already outstanding). Returns the request |
| `POST /api/events/requests/<reference>/resubmit` | `event_organiser` — on one of your client organisation's requests awaiting clarification, answer with `{"response"}` and optionally amend any submission field, each checked as on submission; the request goes back to under review, each amendment and the answer are recorded in its history, and its current coordinator is notified with the answer (`409` for any other status; `403` if your account has no organisation). Returns the request |
| `POST /api/events/requests/<reference>/change-requests` | `event_organiser` — on an event you submitted that is Submitted to Confirmed, ask for a change with `{"reason"}` and a new value for any of `proposed_date`, `end_date`, `start_time`, `end_time`, `expected_attendance`, `venue_requirements`, `equipment_requirements` and `programme_notes`, each checked as the coordinator's edit checks it; at least one must differ from the event's. The event keeps its details; the request is kept Pending with each value asked for and the event's value now, and the assigned coordinator is notified with the fields and the reason. `201` with the change request; `403 not_event_organiser` on a colleague's event, `409 change_request_not_allowed` naming any other status, `400` for a bad or missing value, no reason or nothing to change, `409 conflict` while another request is Pending ([ADR-0126](docs/adr/0126-request-a-change-after-submitting.md)) |
| `POST /api/events/requests/<reference>/change-requests/<id>/withdraw` | `event_organiser` — on an event you submitted, withdraw its Pending change request; no body. It becomes Withdrawn with when, and the assigned coordinator is notified. `200` with the change request; `409 change_request_not_pending` naming its status once it is no longer Pending, `404` for an id the event doesn't have ([ADR-0126](docs/adr/0126-request-a-change-after-submitting.md)) |
| `PATCH /api/events/requests/<reference>/registration` | `event_coordinator` — on a request assigned to you, enable or disable registration, set its capacity and its optional withdrawal cut-off, sending any of `registration_enabled`, `registration_capacity` and `withdrawal_cut_off`; a missing `registration_enabled` follows the organiser's `registration_required` until the event has a capacity. Enabling needs a capacity (`400`) and a confirmed event (`409 registration_not_enablable`); each change is recorded in its history with who made it and when. Returns `reference`, `registration_required`, `registration_enabled`, `registration_capacity` and `withdrawal_cut_off` (business time, or `null`). A capacity below the number already registered is `400` on `registration_capacity` (SCRUM-69 AC5); the venue doesn't limit it (AC3, [ADR-0043](docs/adr/0043-registration-settings-set-by-the-assigned-coordinator.md)). A cut-off at or after the event's start is `400` on `withdrawal_cut_off`; `null` clears it ([ADR-0086](docs/adr/0086-optional-withdrawal-cut-off.md)) |
| `GET  /api/events/catalogue`   | public (a valid token only decides `is_registered`) — the confirmed events with registration enabled that haven't ended, soonest first, one page at a time: `q` (name and description), `when` (`upcoming`, `today`, `this_week`, `this_weekend`) or a `starts_from`/`starts_to` range, `page`, `page_size`. Each event shows its capacity, `places_left`, `is_full` and `is_registered`; a full event stays listed; `venue` is `null` until the venue stack merges ([ADR-0032](docs/adr/0032-event-catalogue-contract.md)) |
| `POST /api/events/catalogue/<id>/registrations` | `attendee` — register for the event; no body, the account is the registration. `201` with the registration (`404` if the event isn't confirmed with registration enabled; `409 already_registered`; `409 event_full`; of two attendees asking for the last place exactly one succeeds) |
| `DELETE /api/events/catalogue/<id>/registrations` | `attendee` — withdraw from the event; the row is kept and the place is freed. `200` with the registration, now `withdrawn` (`404` if the caller isn't registered; `409 already_withdrawn`; `409 withdrawal_closed` once the event's withdrawal cut-off has passed, or it has started when there is none, with `details.withdrawal_closed_at`). Registering again reuses the row ([ADR-0032](docs/adr/0032-event-catalogue-contract.md)) |
| `GET  /api/events/registrations` | `attendee` — your own registrations, for every event you have one on, whatever its status, withdrawn ones included ([ADR-0109](docs/adr/0109-attendee-event-page.md)): `?when=upcoming` (the default, soonest first) or `past` (most recent first). The event's id, `reference`, name, start, end and `event_status`, the registration's status and when it was made; an empty list carries a `message` (ADR-0044) |
| `GET  /api/events/registrations/<reference>` | `attendee` — one event you registered for, whatever its status (withdrawn too): the catalogue's public fields (id, reference, name, description, start, end), `event_status`, each booked venue's `name` and `location`, your registration's `status`, `registered_at` and `withdrawn_at`, `withdrawals_close_at` (the cut-off, or the start), `can_withdraw` (a held place, an event still going ahead, before `withdrawals_close_at`) and `is_being_reviewed` (a change sent the event back to Approved or Safety Review). `404` "Event not found." if you never registered for it or it doesn't exist; `403` for every other role ([ADR-0109](docs/adr/0109-attendee-event-page.md)) |
| `GET  /api/events/requests/<reference>/registrations` | `event_organiser` (your client organisation's events), `event_coordinator` (events assigned to you) — who has registered, oldest first: name, email, registration date and status, with `registered_count`, `capacity` and `places_left` (`null` for an event that never had a capacity). `404` if the event isn't yours or doesn't exist; `403` for every other role, attendees included |
| `POST /api/organisations`      | internal roles — record a client organisation                   |
| `GET  /api/organisations`      | internal roles — list client organisations, by name             |
| `POST /api/venues`             | `venue_staff` — add a venue                                     |
| `GET  /api/venues`             | any authenticated user — list active venues, by name            |
| `GET  /api/venues/<id>`        | any authenticated user — one venue, active or not               |
| `PATCH /api/venues/<id>`       | `venue_staff` — change only the fields sent; if setup/turnaround changed, lists confirmed bookings that now overlap each other or run into a block |
| `POST /api/venues/<id>/deactivate` | `venue_staff` — hide from listing and search, with a `category` and a `reason` note; flags its arrangements that haven't ended Needs Alternative Venue (ADR-0053) |
| `POST /api/venues/<id>/reactivate` | `venue_staff` — show again; clears the flags the deactivation left |
| `GET  /api/venues/<id>/calendar?range_start=…&range_end=…` | internal roles — bookings and blocked periods in the range |
| `POST /api/venues/search`      | `event_coordinator` — venues that meet an event's requirements and are free |
| `POST /api/venues/<id>/blocks` | `venue_staff` — block a period with a `category` and a `reason` note; lists the confirmed bookings it cuts into, and flags every confirmed booking or Pending request it cuts into Needs Alternative Venue, telling each event's coordinator (ADR-0053) |
| `GET  /api/venues/<id>/blocks` | `venue_staff` — the venue's blocks with ids and reasons, in start order |
| `DELETE /api/venues/<id>/blocks/<block_id>` | `venue_staff` — remove a block; the venue is available again and the block's flags are cleared |
| `POST /api/venues/<id>/suitability` | `event_coordinator`, `venue_staff` — whether the venue meets an event's requirements, with each reason it doesn't |
| `POST /api/venues/events/<reference>/booking-requests` | `event_coordinator` — raise a Pending venue booking request for your approved event; returns the request with the event's timing and accessibility needs; 400 naming the venue's hours if the period falls outside them. With `replaces_request_id`, a replacement for a flagged arrangement, also allowed in Safety Review (ADR-0053) |
| `GET  /api/venues/events/<reference>/booking-requests` | `event_coordinator` — the event's booking requests, earliest first, with the same event details; 404 if the event is not yours |
| `PATCH /api/venues/events/<reference>/booking-requests/<id>` | `event_coordinator` — change a pending arrangement's purpose, occupancy, layout or justification; the venue and period don't move |
| `POST  /api/venues/events/<reference>/booking-requests/<id>/withdraw` | `event_coordinator` — retract one arrangement before Venue Staff decide it; 409 if it isn't pending, conflicting or rejected |
| `POST  /api/venues/events/<reference>/booking-requests/cancel-all` | `event_coordinator` — retire every arrangement the event still has |
| `POST  /api/venues/events/<reference>/booking-requests/<id>/cancel` | `event_coordinator` — cancel one approved booking with `{"reason"}` while the event is approved or in Safety Review: the booking is cancelled, freeing the venue, and the arrangement becomes `cancelled`; the event's other arrangements are untouched. An event in Safety Review goes back to `approved` if the Safety Officer had approved it (the approval is withdrawn) or this was its last active venue. Recorded in its history with the reason; every Venue Staff user is told, and every Safety Officer when the event was in Safety Review. `400` without a reason; `409` naming the status for an arrangement that isn't approved or an event in any other status ([ADR-0117](docs/adr/0117-cancel-one-approved-venue-booking.md)) |
| `GET  /api/venues/booking-requests` | `venue_staff` — every Pending or Conflicting request waiting for a decision, earliest event first, with the event's timing and accessibility needs |
| `POST /api/venues/booking-requests/<id>/decision` | `venue_staff` — approve a request (books the venue) or reject it; a rejection needs a reason; 409 if it isn't pending or conflicting, or if approving clashes with a confirmed booking at the venue (setup and turnaround included), naming that booking (ADR-0045). Approving a replacement releases the arrangement it replaces and withdraws the event's safety approval (ADR-0053) |
| `GET  /api/venues/booking-requests/approved` | `venue_staff` — every approved booking, earliest event first, with the event's timing and accessibility needs and the booking's preparation status and notes: where Venue Staff find the bookings to prepare ([ADR-0080](docs/adr/0080-venue-preparation-screen.md)) |
| `PUT  /api/venues/booking-requests/<id>/preparation` | `venue_staff` — record `{"status": "not_started" \| "in_progress" \| "ready", "notes"}` on an approved booking, each update kept in the event's history with who and when; the coordinator reads it on their event's booking requests; 409 if the booking isn't approved or the Safety Officer hasn't approved the event ([ADR-0049](docs/adr/0049-venue-preparation-details.md)) |
| `GET  /api/venues/booking-requests/flagged` | `venue_staff` — every booking a change flagged, earliest event first, as `{"booking", "reconfirm_with": {"starts_at", "ends_at", "expected_occupancy", "period_adjustable"}}`: the period moved by as much as the event's start moved, whether it may be adjusted (only once the event's date or times changed) and, for a booking that held everyone, the new attendance; one needing an alternative venue is left out ([ADR-0112](docs/adr/0112-reconfirm-or-reject-a-flagged-booking.md)) |
| `POST /api/venues/booking-requests/<id>/reconfirm` | `venue_staff` — reconfirm a flagged booking for `{"starts_at", "ends_at", "reason"?}`: the period stays unless the event's date or times changed (400), and must lie within the event and the venue's hours (400) and clear of bookings, holds, blocks and the event's other arrangements at the venue, setup and turnaround included (409, naming it); a venue too small for the occupancy needs a reason; 409 while a replacement waits. The flags clear, an undecided request only moves, and the coordinator is told (ADR-0112) |
| `POST /api/venues/booking-requests/<id>/reject` | `venue_staff` — reject a flagged booking with `{"reason"}`, freeing its venue; it stays as Rejected until the coordinator withdraws or replaces it, and the coordinator is told (ADR-0112) |
| `POST /api/equipment/types`    | `technical_support_staff` — add an equipment type               |
| `GET  /api/equipment/types`    | internal roles — every equipment type with its total quantity, by name |
| `GET  /api/equipment/types/<id>` | internal roles — one equipment type                           |
| `PATCH /api/equipment/types/<id>` | `technical_support_staff` — change only the fields sent; sending `venue_id` or `store_name` replaces the location |
| `GET  /api/equipment/events/<reference>/availability` | `event_coordinator` (events assigned to you; any other is `404`), `technical_support_staff` (any event but a draft) — for every equipment type, how many are free for the event's own period, what it asks for and any shortfall |
| `POST /api/equipment/events/<reference>/reservations` | `technical_support_staff` — reserve up to what is free (`201`); more is `400` naming how many are free, and so is more than the event's line asks for, with what is already reserved (ADR-0114) |
| `GET  /api/equipment/events/<reference>/reassessments` | `event_coordinator` (events assigned to you; any other is `404`), `technical_support_staff` (any event but a draft) — each equipment type whose reservations a change marked: the reservations as held, the event's period now, what is free for it and the shortfall ([ADR-0114](docs/adr/0114-reassess-equipment-reservations-after-a-change.md)) |
| `POST /api/equipment/events/<reference>/reassessments/<type_id>/confirm` | `technical_support_staff` — move the type's marked reservations to the event's period now, keeping what the line's outcome provides, or, for a type with no line, what is free and releasing the rest, and tell the coordinator once what was kept and released; `404` with nothing marked, `409` when the line has no outcome or fewer are free than the line keeps (ADR-0114) |
| `PUT  /api/equipment/reservations/<id>/preparation` | `technical_support_staff` — record `{"status": "not_started" \| "in_progress" \| "ready", "notes"}` on a reservation, each update kept in the event's history with who and when; the coordinator reads it with the event's reservations; 409 if the Safety Officer hasn't approved the event ([ADR-0050](docs/adr/0050-equipment-preparation-details.md)) |
| `GET  /api/equipment/events/<reference>/reservations` | `event_coordinator` (events assigned to you; any other is `404`), `technical_support_staff` (any event but a draft) — the equipment reserved for the event, oldest first, with who reserved it by name |
| `POST /api/equipment/types/<id>/out-of-service` | `technical_support_staff` — take `quantity` units out of service as `damaged` or `under_maintenance` (`201`); they stop counting as free, reservations left short are flagged `needs_attention` and their coordinator is told; more than are in service is `400` |
| `GET  /api/equipment/types/<id>/out-of-service` | `technical_support_staff` — the units still out of service, oldest first, with who recorded them and when |
| `POST /api/equipment/out-of-service/<id>/return` | `technical_support_staff` — put those units back in service (`409` if already back); records who and when |
| `GET  /api/notifications`      | any authenticated user — your notifications, newest first      |
| `GET  /api/notifications/unread-count` | any authenticated user — how many of yours are unread   |
| `POST /api/notifications/<id>/read` | any authenticated user — mark one of yours read (`404` if it isn't yours) |

Roles: `event_organiser`, `attendee`, `event_coordinator`, `event_coordinator_lead`, `venue_staff`, `technical_support_staff`.

Password policy: at least 8 characters, with at least one letter and one digit.

An `event_organiser` registers with the `organisation_id` of an existing client organisation, which an internal user records first; an attendee must leave it out ([ADR-0013](docs/adr/0013-client-organisations-recorded-by-internal-users.md)). Every organiser of an organisation sees all of its event requests, and no other organisation's ([ADR-0020](docs/adr/0020-organisers-see-their-organisations-events.md)).

A draft is an event request in status `draft`: it can be saved with only a name, reopened and changed field by field, and submitted in place once it is complete, keeping its reference. It is visible only to the organiser who saved it — never to a colleague, and never to Event Coordinators or Technical Support Staff — until it is submitted ([ADR-0024](docs/adr/0024-draft-event-requests.md)).

A submitted event request is assigned to nobody. It waits in the Event Coordinator Lead's unassigned queue, which only a Lead can see, and every Lead is notified that it is waiting. A Lead gives it to one Event Coordinator, named by email; that is written to the event's history with the Lead as the actor, and the request leaves the queue ([ADR-0036](docs/adr/0036-event-coordinator-lead.md), superseding the least-loaded rule of [ADR-0018](docs/adr/0018-least-loaded-coordinator-and-event-history.md)). The organiser who submitted it is told a coordinator has been assigned, on that assignment and again on each reassignment; their colleagues aren't ([ADR-0030](docs/adr/0030-organiser-told-about-assignment.md)). Everything that happens to an event is written to an event history table that later stories append to.

All errors share one shape: `{"error": "<code>", "message": "<text>", "details": {...}}` (`details` only for validation errors).

An equipment type is kept at exactly one place: a catalogued venue (`venue_id`) or a named store (`store_name`). Equipment type names are unique ([ADR-0014](docs/adr/0014-equipment-type-location-and-quantity.md)).

An event has at most one equipment line per equipment type (edit the line to change the quantity), and its lines can be added, changed or removed only by the request's assigned coordinator and only while the request is `submitted`, `under_review` or `approved` ([ADR-0019](docs/adr/0019-event-equipment-lines.md), [ADR-0028](docs/adr/0028-review-and-decide.md)).

Technical Support Staff share one list of the equipment awaiting them: an event is on it while any of its lines is still `requested`, its date is today or later, and it isn't completed, cancelled or rejected ([ADR-0022](docs/adr/0022-equipment-awaiting-action.md)).

An event's assigned coordinator can edit its notes, dates, times, attendance and requirements text while it is `submitted`, `under_review`, `approved` or `confirmed`; a value equal to what's already saved is not a change. Every changed field is written to the event's history, flagged `significant` if it could affect a venue booking or the equipment already requested; a significant change that could affect equipment notifies every Technical Support Staff member once per edit, but only if the event already has an equipment line to reassess ([ADR-0025](docs/adr/0025-event-edits-significant-changes-and-history.md)).

An event's assigned coordinator marks it completed once it is `confirmed` and its end (`end_date` and `end_time`, in business time) has passed, the end instant included. The change is recorded in the event history with who did it and when, and a completed event can no longer be edited ([ADR-0027](docs/adr/0027-event-completion.md)).

An event request's statuses are `draft`, `submitted`, `under_review`, `awaiting_clarification`, `approved`, `safety_review`, `confirmed`, `completed`, `cancelled` and `rejected` ([ADR-0048](docs/adr/0048-ten-event-statuses.md)). Its assigned coordinator may move a submitted request to `under_review`, and approve or reject it from either status; a rejection needs a reason, a first approval may give one. A decision can be changed, with a reason, until the event has an equipment request or a venue booking request that hasn't been withdrawn, released or cancelled ([ADR-0084](docs/adr/0084-venue-booking-requests-lock-the-decision.md)). Every decision is kept in the event's history, the latest is shown on the event record, and the organiser who submitted it is notified with the reason ([ADR-0028](docs/adr/0028-review-and-decide.md)). Later, while the event is approved or in Safety Review, the coordinator can still reject it with a reason when an essential arrangement can't be met; that releases its venues and returns its equipment in the same commit ([ADR-0093](docs/adr/0093-reject-an-event-during-planning.md)).

While a request is under review, its assigned coordinator may ask the organiser for clarification; the request becomes `awaiting_clarification` and the organiser who submitted it is notified with the question. Any organiser of its client organisation answers and resubmits it in one step, amending any submission field if they wish; it goes back to `under_review` and its current coordinator is notified with the answer. Meanwhile the coordinator can't edit it, change its equipment or approve it, but may still reject it or reassign it. Every question and answer is kept in the event's history and shown on the event record ([ADR-0029](docs/adr/0029-clarification-requests.md)).

Date-times (bookings, blocks, calendar ranges) should carry an offset, such as `Z` or `+08:00`. One sent without an offset is read as business time (`APP_TIMEZONE`, Singapore by default). They're stored in UTC and come back in business time, e.g. `2026-10-01T17:00:00+08:00` ([ADR-0009](docs/adr/0009-booking-times-in-utc.md)). Notification times (`created_at`, `read_at`) come back the same way. A notification's `detail` says more about what happened, such as the reason for a decision or a clarification's question or answer, and is `null` for kinds that carry none.

## 5. Run the tests

The suite is unit tests only, and **Postgres does not need to be running**. Most tests mock the database; the venue, equipment, notifications, coordinator-assignment and event equipment service tests run against an in-memory SQLite database, so their queries really execute. The one exception is `tests/e2e/`: its journey walks an event request from draft to approval through the real routes with Flask's test client, on the same in-memory database (ADR-0031). `pytest -m "not e2e"` runs the unit tests alone.

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
pytest -m scrum_31   # review and decide a submitted request
pytest -m scrum_32   # ask the organiser for clarification
pytest -m scrum_34   # block a venue
pytest -m scrum_35   # search and filter venues
pytest -m scrum_36   # check whether a venue suits an event
pytest -m scrum_37   # record what equipment an event needs
pytest -m scrum_38   # see the equipment requests awaiting my action
pytest -m scrum_39   # be notified about review and approval decisions
pytest -m scrum_67   # setup and turnaround time
pytest -m scrum_66   # client organisations
pytest -m scrum_7    # see only my own organisation's events
pytest -m scrum_87   # reassign an event to a different coordinator
pytest -m scrum_88   # staff accounts come from a command, not self-registration
pytest -m scrum_33   # update event information and flag significant changes
pytest -m scrum_68   # mark an event as completed after it has taken place
pytest -m scrum_41   # end-to-end test: request to approval
pytest -m scrum_96   # the Lead oversees and reassigns coordinators' events
pytest -m scrum_95   # newly submitted requests go to the Event Coordinator Lead unassigned
pytest -m e2e        # every journey driven through the HTTP layer
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
