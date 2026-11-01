# ConnectSphere frontend

The web app for ConnectSphere: a landing page, the public event catalogue, sign-up for Event
Organisers and Attendees, and separate log-in pages for external users and staff.

React 19 + TypeScript, Vite, Tailwind CSS v4, Redux Toolkit (session only), TanStack Query,
React Router v8. Conventions and the three test layers are in [CLAUDE.md](CLAUDE.md).

## Run it

Node 22.22 or later (`.nvmrc` pins 24).

```bash
cd frontend
npm ci

# Against the backend (see the root README to start it). /api is proxied to BACKEND_URL.
npm run dev                                       # backend on :5000
BACKEND_URL=http://localhost:5055 npm run dev     # backend elsewhere, e.g. on macOS where :5000 is AirPlay

# Without a backend: every API call is answered by the mock handlers in src/mocks.
npm run dev:mock
```

Open http://localhost:5173.

## Test it

```bash
npm test                   # unit + component tests
npm run test:coverage      # with the 100% coverage floor
npm run test:e2e           # Playwright, desktop and mobile (first time: npx playwright install chromium)
BACKEND_URL=http://localhost:5055 npm run test:integration   # against a running backend
```

Some integration tests record client organisations, which only staff may do, so they sign in as a
staff account. Make one on that backend once, then pass it in (CI makes its own for each run):

```bash
cd backend && flask create-staff-user --email you@connectsphere.test --full-name "Your Name" --role event_coordinator
INTEGRATION_STAFF_EMAIL=you@connectsphere.test INTEGRATION_STAFF_PASSWORD=<its password> \
  BACKEND_URL=http://localhost:5055 npm run test:integration
```

The safety checks (SCRUM-97, SCRUM-98) also need a Lead, Venue Staff and a Safety Officer, made
the same way with `--role event_coordinator_lead`, `venue_staff` and `safety_officer`. Pass them as
`INTEGRATION_LEAD_EMAIL` / `_PASSWORD`, `INTEGRATION_VENUE_STAFF_EMAIL` / `_PASSWORD` and
`INTEGRATION_SAFETY_OFFICER_EMAIL` / `_PASSWORD`; the checks that need them skip without them.

## Accounts

- **Event Organisers and Attendees** sign up at `/signup`. An Organiser needs the organisation
  ID ConnectSphere staff gave them (ADR-0013).
- **Staff** (Event Coordinator Lead, Event Coordinator, Venue Staff, Technical Support Staff, Safety Officer) can't sign up. Their
  accounts are created with `flask create-staff-user` (ADR-0023), and they log in at
  `/staff/login`.
