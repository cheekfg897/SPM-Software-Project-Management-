# User Stories — Sprint 1 (Auth Foundation)

Format: As a / I want / So that + acceptance criteria.
Each story maps to a pytest marker in `pytest.ini` so tests can be traced back to it.

<!-- TODO: replace marker/story name with the actual Jira story ID once assigned -->

---

## Story 1 — Create an account
**Marker:** `story_create_account`

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

## Story 2 — Log in to the system
**Marker:** `story_login`

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

## Story 3 — Enforce permissions for every role
**Marker:** `story_permissions`

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
