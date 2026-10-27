# C4 level 2: containers

The separately running or deployable pieces. Versions are from `frontend/package.json`,
`backend/requirements.txt` and `docker-compose.yml`.

```mermaid
flowchart TB
  classDef person fill:#08427b,stroke:#052e56,color:#ffffff
  classDef container fill:#438dd5,stroke:#2e6295,color:#ffffff
  classDef tool fill:#b8b8b8,stroke:#8a8a8a,color:#222222
  classDef ext fill:#6b6b6b,stroke:#4a4a4a,color:#ffffff

  users["<b>Users</b><br/>[Person]<br/>Event Organisers, Attendees<br/>and the five staff roles"]:::person

  subgraph cs["ConnectSphere (the running system)"]
    direction TB
    web["<b>Web App</b><br/>[React 19, TypeScript, Vite, Tailwind CSS 4]<br/>Single-page app. Redux Toolkit holds the session.<br/>TanStack Query fetches server data"]:::container
    api["<b>Backend API</b><br/>[Python 3.12, Flask 3.1]<br/>Modular monolith, REST and JSON under /api.<br/>JWT log-in, role checks, marshmallow<br/>validation, all business rules"]:::container
    db[("<b>Database</b><br/>[PostgreSQL 16]<br/>Users, events and history, venues, bookings,<br/>equipment, registrations, notifications.<br/>Schema managed by Alembic")]:::container
    job["<b>Hold-expiry job</b><br/>[flask expire-holds]<br/>Expires tentative holds, then sends<br/>24-hour warnings. Safe to run twice"]:::container
  end

  subgraph delivery["Delivery tooling (not part of the running system)"]
    direction LR
    ci["<b>CI pipelines</b><br/>[GitHub Actions]<br/>Backend lint, migrations, tests, coverage gates.<br/>Frontend lint, unit, integration and Playwright.<br/>PR title check"]:::tool
    standup["<b>Standup reminder</b><br/>[GitHub Actions schedule]<br/>Posts the daily standup questions"]:::tool
  end

  telegram["<b>Telegram group chat</b><br/>[External system]"]:::ext

  users -->|"use<br/>HTTPS, browser"| web
  web -->|"calls<br/>JSON over HTTP, Bearer JWT"| api
  api -->|"reads and writes<br/>SQLAlchemy, psycopg2"| db
  job -->|"updates holds,<br/>writes notifications"| db
  ci -.->|"builds and tests"| cs
  standup -->|"sends reminder<br/>Telegram Bot API"| telegram

  style cs fill:none,stroke:#888888,stroke-dasharray:5 3
  style delivery fill:none,stroke:#888888,stroke-dasharray:5 3
```

**Notes**

- The backend also ships a `flask create-staff-user` command. Staff accounts are created that way, not
  through sign-up (ADR-0023).
- `docker-compose.yml` runs `postgres:16-alpine` and the backend on `python:3.12-slim` for local development.
- Alembic migrations run up to `0045_add_venue_booking_released` (as of 25 Oct 2026).
