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

---

# User Stories — Sprint 2 (Venue Management)

Same format and marker convention as Sprint 1. Roles/permissions are reused
from `app/modules/auth/permissions.py` (`Role`, `INTERNAL_ROLES`); nothing
new is defined for this module.

## Story 4 — Update venue catalogue
**Marker:** `story_venue_catalogue`

**As a** Venue Staff member,
**I want to** update the record of each ConnectSphere venue,
**so that** Event Coordinators can plan against accurate venue information rather than asking us.

### Acceptance criteria
- [ ] Venue Staff can edit a venue's name, location, maximum capacity, supported room layouts, facilities, accessibility features and operating hours, and save the changes.
- [ ] Required fields (name, location, capacity) cannot be saved blank, and invalid values (e.g. negative or zero capacity) are rejected with a clear error message.
- [ ] Once saved, updated venue details are immediately visible to Event Coordinators browsing or opening that venue.
- [ ] Venue details remain read-only for anyone who is not Venue Staff.
- [ ] Venue Staff can deactivate a venue; a deactivated venue no longer appears in venue search but stays attached to bookings already made against it.
- [ ] Venue Staff can reactivate a previously deactivated venue.

### Assumptions / open questions
- Reading a venue (`GET /api/venues`, `GET /api/venues/<id>`) is available to **any authenticated user**, not just Venue Staff — the AC says details are read-only for non-staff, implying they can still be read. Only create/update/deactivate/reactivate are Venue-Staff-only.

---

## Story 5 — View a venue's availability calendar
**Marker:** `story_venue_calendar`

**As an** internal user,
**I want to** see a venue's bookings and unavailable periods across a date range,
**so that** I can tell at a glance when that venue could be used.

### Acceptance criteria
- [ ] Can choose a venue and a date range and see, for each day, the periods that are booked or otherwise unavailable.
- [ ] Confirmed bookings and blocked periods both appear as unavailable.
- [ ] Each unavailable period shows its start time, end time and reason at the level of detail the viewer's role permits.
- [ ] Event Organisers and Attendees cannot open the venue availability calendar.

### Assumptions / open questions
- "Level of detail the viewer's role permits": Venue Staff see the full reason text; `event_coordinator` and `technical_support_staff` (the only other roles that can open the calendar at all) see a coarse category only (`"booking"` / `"maintenance"`), no free text.
- There is no story yet for *creating* a booking or a block — SCRUM-19 (events module) only captures a submitted event request, with no venue-matching/confirmation workflow that would turn one into a booking. A minimal `POST /api/venues/<id>/blocks` (Venue Staff only) is included purely so this story's "blocked periods" AC has a path to exercise via the API; it is not itself a requested story.

---

## Story 6 — Search and filter venues against event requirements
**Marker:** `story_venue_search`

**As an** Event Coordinator,
**I want to** search venues using the requirements of a specific event,
**so that** I can shortlist the venues worth requesting instead of checking each one by hand.

### Acceptance criteria
- [ ] Can filter by date, start and end time, minimum capacity, location, required room layout, accessibility requirement and required facilities.
- [ ] Only venues free for the requested period, allowing for any configured setup and turnaround time, are returned as available.
- [ ] Each result shows venue name, capacity, location and which requested requirements it satisfies.
- [ ] A clear message is shown when nothing matches.
- [ ] The search can be opened from an event with its filters already populated from that event's recorded requirements.

### Assumptions / open questions
- The last AC ("opened from an event with its filters already populated") is a frontend/event-integration concern — SCRUM-19's `EventRequest` does capture venue/accessibility/equipment requirements as free text, not structured filter values, so there's no direct field mapping to source from yet. The backend just exposes `POST /api/venues/search`; pre-population is out of scope here.
- Search is available to any authenticated user (`requires_auth`), not restricted to Event Coordinators specifically — the AC doesn't restrict it the way the calendar story does.

---

## Story 7 — Record setup and turnaround time for a venue
**Marker:** `story_venue_setup_turnaround`

**As a** Venue Staff member,
**I want to** record the setup and turnaround time a venue needs,
**so that** conflict detection and venue search leave enough time between consecutive events.

Raised because Story 6 refuses bookings that violate "any configured setup and turnaround time", and search filters "allowing for any configured setup and turnaround time" — but Story 4's venue record didn't originally capture either field.

### Acceptance criteria
- [ ] A venue records a setup time required before an event and a turnaround time required after it.
- [ ] Both default to a defined value when not set explicitly.
- [ ] Venue availability, venue search and conflict detection all treat the booked period as the event period extended by setup and turnaround time.
- [ ] Changing a venue's turnaround time does not retrospectively invalidate bookings already confirmed, but any resulting overlap is reported to Venue Staff.
- [ ] Only Venue Staff can change these values.

### Open question for the customer
Is turnaround time fixed company-wide, set per venue, or dependent on event type or room layout? What is the default?

**Current implementation**: per-venue (`setup_minutes` / `turnaround_minutes` on the venue record), defaulting to `DEFAULT_VENUE_SETUP_MINUTES` / `DEFAULT_VENUE_TURNAROUND_MINUTES` (30 minutes each) when unset — configurable via environment, not yet configurable per event type or room layout.

### Assumptions / open questions
- "Reported to Venue Staff" — there's no notification system yet (that's its own unbuilt story). The `PATCH /api/venues/<id>` response itself includes an `overlap_warnings` list of confirmed bookings that now overlap under the new buffer, visible to the Venue Staff member who made the change.
