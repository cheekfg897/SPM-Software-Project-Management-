# User Stories — Sprint 1 (Auth Foundation)

Format: As a / I want / So that + acceptance criteria.
Each story maps to a pytest marker in `pytest.ini` so tests can be traced back to it.

> **Jira is the source of truth.** This file is the team's Sprint 1 working copy. The acceptance
> criteria for SCRUM-65, SCRUM-6 and SCRUM-21 below were written before the Jira stories were
> finalised and **no longer match them** (e.g. Jira's SCRUM-65 forbids self-registering internal
> roles; SCRUM-6 adds logout). Check the story in Jira before relying on anything here.

---

## SCRUM-65 — Create an account
**Marker:** `scrum_65`

**As a** new user,
**I want to** create an account by providing my email, password, name, and role,
**so that** I can access the parts of the system relevant to me.

### Acceptance criteria
- [ ] Registration requires `email`, `password`, `full_name`, `role`. `organisation` is optional (relevant to Event Organisers / Attendees).
- [ ] `role` must be one of: `event_organiser`, `attendee`, `event_coordinator`, `venue_staff`, `technical_support_staff`.
- [ ] Email must be a valid format and unique. Duplicate registration returns a clear `409 Conflict`, not a generic `500`.
- [ ] Password must meet the minimum strength policy: **at least 8 characters, containing at least one letter and at least one digit.** A password that fails the policy is rejected with a specific message saying which rule failed.
- [ ] Password is hashed before storage (Werkzeug `scrypt`) and is never returned in any response.
- [ ] On success, a `201 Created` is returned with the user's `id`, `email`, `full_name`, `role`, `organisation` — no password hash.
- [ ] Invalid input (missing fields, bad email, bad role, weak password) returns `400 Bad Request` with per-field error messages.

### Assumptions / open questions
- Registration is treated identically for all five roles (self-service, all required fields). **We have not confirmed with the customer whether internal roles (Event Coordinator, Venue Staff, Technical Support Staff) should be self-registered or provisioned by an admin.** See `# TODO(product)` at the registration endpoint.

---

## SCRUM-6 — Log in to the system
**Marker:** `scrum_6`

**As a** registered user,
**I want to** log in with my email and password,
**so that** I can securely access the system.

### Acceptance criteria
- [ ] Valid credentials return a JWT access token plus the user's `id`, `full_name`, and `role`.
- [ ] The JWT includes the user's `role` as a claim, since permission checks depend on it.
- [ ] Invalid email or invalid password both return the same generic error message (`Invalid email or password.`) with `401`, so an attacker cannot enumerate registered emails.
- [ ] Access token expiry is configurable via `JWT_ACCESS_TOKEN_EXPIRES_SECONDS` and defaults to **1 hour**.
- [ ] Refresh tokens are out of scope for this sprint (`# TODO` left in code as a future story).

---

## SCRUM-21 — Enforce permissions for every role
**Marker:** `scrum_21`

**As** ConnectSphere,
**I want** every protected action to check the caller's role,
**so that** users only access information and functionality appropriate to their role.

### Acceptance criteria
- [ ] A reusable `@requires_role(*roles)` decorator in `app/common/decorators.py` protects any route by allowed role(s).
- [ ] A reusable `@requires_auth` decorator protects any route that only needs a valid token.
- [ ] Missing / invalid / expired token → `401`. Valid token but wrong role → `403`. Both return the same JSON error shape: `{"error": "<code>", "message": "<text>"}`.
- [ ] The pattern is demonstrated by `GET /api/auth/me` (any authenticated user) and `GET /api/auth/internal-only` (only `event_coordinator`, `venue_staff`, `technical_support_staff`).
- [ ] Permission logic lives in one place (`app/common/decorators.py` + `app/modules/auth/permissions.py`) and is not duplicated per route.
- [ ] Failed authorization attempts are logged with the role attempted, the endpoint, and a timestamp (groundwork for the Auditability requirement).

---

# Events

## SCRUM-19 — Submit an event request
**Marker:** `scrum_19`

**As an** Event Organiser,
**I want to** submit an event request describing what my event needs,
**so that** ConnectSphere can start planning it.

### Acceptance criteria
- [x] Can supply event name, purpose, description, proposed date, start and end time, expected attendance, venue requirements, accessibility needs, equipment requirements, and whether attendee registration is needed.
- [x] Cannot submit unless event name, proposed date, start time, end time and expected attendance are present.
- [x] Cannot submit a proposed date in the past.
- [x] Cannot submit an end time earlier than the start time.
- [x] After submission the request appears in the Organiser's event list with status Submitted and a reference it can be identified by.

### Decisions (see `docs/adr/`)
- **ADR-0001:** "past" means before today in Singapore time (`APP_TIMEZONE`). Today is allowed.
- **ADR-0002:** the event must end strictly after it starts. Overnight events use an optional `end_date`, which defaults to the proposed date.
- **ADR-0003:** expected attendance is a whole number of at least 1, with no upper limit.
- **ADR-0004:** the reference looks like `EVR-7K2QX9AB`. It is random, unique, and retried up to 3 times if it collides.

### API
| Route | Access | Result |
|---|---|---|
| `POST /api/events/requests` | `event_organiser` | `201` with the request, including `reference` and `status: "submitted"` |
| `GET /api/events/requests` | `event_organiser` | `200` with `{"event_requests": [...]}`, containing only the caller's own requests, newest first |
