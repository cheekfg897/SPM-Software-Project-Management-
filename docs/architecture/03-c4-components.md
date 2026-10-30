# C4 level 3: components of the Backend API

## 3a. Modules and how they depend on each other

Each folder under `backend/app/modules/` is one Flask blueprint with its own routes, schemas, services
and models. Arrows between modules are real imports found in the code; a two-headed arrow means each module
imports the other. Endpoint counts are the `@bp.get/post/patch/put/delete` routes in each `routes.py`.

```mermaid
flowchart LR
  classDef container fill:#438dd5,stroke:#2e6295,color:#ffffff
  classDef comp fill:#85bbf0,stroke:#5a9bd0,color:#0b2a4a
  classDef hub fill:#4f9be0,stroke:#2e6295,color:#ffffff

  web["<b>Web App</b><br/>[React 19]"]:::container
  db[("<b>Database</b><br/>[PostgreSQL 16]")]:::container

  subgraph api["Backend API [Flask 3.1]"]
    direction LR
    auth["<b>auth</b><br/>/api/auth, 5 routes<br/>Sign-up, log-in, log-out, JWT, roles"]:::comp
    orgs["<b>organisations</b><br/>/api/organisations, 2 routes<br/>Client organisations"]:::comp
    events["<b>events</b><br/>/api/events, 34 routes<br/>Requests, review, assignment,<br/>safety review, confirmation"]:::hub
    venue["<b>venue</b><br/>/api/venues, 23 routes<br/>Catalogue, search, bookings,<br/>holds, flags"]:::comp
    equipment["<b>equipment</b><br/>/api/equipment, 11 routes<br/>Catalogue, reservation,<br/>out-of-service"]:::comp
    registration["<b>registration</b><br/>/api/events, 6 routes<br/>Register, withdraw, registrants,<br/>the attendee's own event"]:::comp
    notifications["<b>notifications</b><br/>/api/notifications, 3 routes<br/>Notify, list, mark read"]:::comp
  end

  web -->|"JSON over HTTP, Bearer JWT"| api
  api -->|"SQLAlchemy"| db

  auth <--> orgs
  events <--> venue
  events <--> equipment
  events <--> registration
  events --> notifications
  venue --> notifications
  equipment --> venue
  registration --> venue

  style api fill:none,stroke:#888888,stroke-dasharray:5 3
```

**What the arrows say about the design**

- `events` is the hub: `venue`, `equipment` and `registration` all depend on it, and it calls back into each of
  them and into `notifications`. `organisations` only talks to `auth`.
- The pairs `events` and `venue`, `events` and `equipment`, `events` and `registration` import each other.
  The code resolves this with function-local imports and marks them `# circular at import time`.
  It works, but it is the main place a change in one module can break another.
- Every module also uses the shared `common` package (role decorators, error types, business-time clock,
  validation) and `auth` for roles and tokens. Those arrows are left off to keep the picture readable.

## 3b. Inside one module (venue as the example)

Every module has the same layering. A request enters through `routes.py`, is checked by a marshmallow
schema, runs through a service function that holds the business rules, and touches the database through
the models. Only `auth` and `venue` also have a `commands.py`.

```mermaid
flowchart TB
  classDef container fill:#438dd5,stroke:#2e6295,color:#ffffff
  classDef comp fill:#85bbf0,stroke:#5a9bd0,color:#0b2a4a
  classDef shared fill:#c9def2,stroke:#8fb4d9,color:#0b2a4a

  web["<b>Web App</b><br/>[React 19]<br/>Venue search, booking and<br/>Venue Staff screens"]:::container
  job["<b>Hold-expiry job</b><br/>[flask expire-holds]<br/>Runs hourly"]:::container
  common["<b>common</b><br/>[Python package]<br/>requires_auth, requires_role,<br/>errors, clock"]:::shared
  db[("<b>Database</b><br/>[PostgreSQL 16]<br/>venues, bookings, venue_booking_requests<br/>and 4 related tables")]:::container

  subgraph venue["venue module"]
    direction TB
    routes["<b>routes.py</b><br/>[Flask blueprint]<br/>23 endpoints, role checks, JSON"]:::comp
    schemas["<b>schemas.py</b><br/>[marshmallow]<br/>Validates bodies, shapes responses"]:::comp
    services["<b>services.py</b><br/>[Python functions]<br/>Suitability, clash detection, decisions,<br/>holds, release, flagging"]:::comp
    hours["<b>opening_hours.py</b><br/>[Python]<br/>Does a period fit opening hours"]:::comp
    models["<b>models.py</b><br/>[SQLAlchemy]<br/>Venue, Booking, VenueBookingRequest<br/>and 4 more tables"]:::comp
    commands["<b>commands.py</b><br/>[Click CLI]<br/>expire-holds command"]:::comp
  end

  web -->|"JSON over HTTP"| routes
  routes -->|"role check"| common
  routes -->|"validates with"| schemas
  routes -->|"calls"| services
  services -->|"checks periods"| hours
  services -->|"reads and writes"| models
  models -->|"SQLAlchemy"| db
  job -->|"runs"| commands
  commands -->|"expire_holds,<br/>send_hold_expiry_warnings"| services

  style venue fill:none,stroke:#888888,stroke-dasharray:5 3
```
