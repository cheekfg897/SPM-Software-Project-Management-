# C4 level 2: containers

The separately running or deployable pieces. Versions are from `frontend/package.json`,
`backend/requirements.txt` and `docker-compose.yml`.

```mermaid
---
title: "Container diagram: ConnectSphere"
---
flowchart TB
  classDef ext fill:#6b6b6b,stroke:#4a4a4a,color:#ffffff
  classDef person fill:#08427b,stroke:#052e56,color:#ffffff
  classDef container fill:#438dd5,stroke:#2e6295,color:#ffffff

  clients["<b>Clients and public</b><br/>[Person]<br/>Event Organisers and Attendees,<br/>who sign up themselves"]:::ext
  staff["<b>ConnectSphere staff</b><br/>[Person]<br/>The five staff roles, whose accounts<br/>are created by an admin"]:::person

  subgraph cs["ConnectSphere [Software System]"]
    direction TB
    web["<b>Web App</b><br/>[Container: React 19, TypeScript, Vite, Tailwind CSS 4]<br/>Single-page app that runs in the user's browser."]:::container
    api["<b>Backend API</b><br/>[Container: Python 3.12, Flask 3.1]<br/>REST and JSON under /api. JWT log-in,<br/>role checks, validation, business rules."]:::container
    db[("<b>Database</b><br/>[Container: PostgreSQL 16]<br/>Users, client organisations, events and history,<br/>venues, bookings, equipment, registrations,<br/>notifications.")]:::container
    job["<b>Hold-expiry job</b><br/>[Container: Python 3.12, Flask CLI, shares the Backend API codebase]<br/>Runs hourly via cron. Expires tentative venue holds and<br/>warns the coordinator 24 hours before expiry. Safe to run twice."]:::container
  end

  clients -->|"sign up, request events, register for events<br/>HTTPS (web browser)"| web
  db ~~~ k1
  k1 ~~~ k2 ~~~ k3 ~~~ k4
  staff -->|"review, assign and arrange events<br/>HTTPS (web browser)"| web
  web -->|"calls<br/>JSON over HTTP, Bearer JWT"| api
  api -->|"reads and writes<br/>SQLAlchemy, psycopg2"| db
  job -->|"marks holds Expired, writes event history and notifications<br/>SQLAlchemy, psycopg2"| db

  subgraph key["Key"]
    direction LR
    k1["External person"]:::ext
    k2["Staff"]:::person
    k3["Container"]:::container
    k4["Dashed line = system boundary"]
  end


  style cs fill:none,stroke:#888888,stroke-dasharray:5 3
  style key fill:none,stroke:#888888,stroke-dasharray:5 3
  style k4 fill:none,stroke:none
```

**Notes**

- Staff accounts are created by an admin with the `flask create-staff-user` command, not through
  sign-up (ADR-0023). There is no separate Administrator or CLI container on the diagram.
- `docker-compose.yml` runs `postgres:16-alpine` and the backend on `python:3.12-slim` for local development.
- Alembic migrations run up to `0048_create_revoked_tokens_table` (as of 31 Oct 2026).
- The cron schedule is `.github/workflows/expire-holds.yml` (minute 7 of every hour, UTC). It stops after
  its first step until a `DATABASE_URL` repository secret exists, so the job does not yet run against a
  deployed database.
