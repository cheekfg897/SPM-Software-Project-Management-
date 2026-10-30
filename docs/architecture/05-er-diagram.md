# Entity-relationship diagrams

The 18 tables created by the Alembic migrations (latest `0048`), split into three views so each stays readable.
Only keys and the columns that explain a relationship are shown. A table shown with just its key is a stub: it
appears in full in another view. `bookings.event_id` has no foreign key, so it is a plain column with no line.

## 5a. People, events, registration and notifications

`revoked_tokens` holds one row per access token logged out before it expired (SCRUM-89, ADR-0110).

```mermaid
erDiagram
  CLIENT_ORGANISATIONS |o--o{ USERS : "employs"
  CLIENT_ORGANISATIONS |o--o{ EVENT_REQUESTS : "client of"
  USERS ||--o{ EVENT_REQUESTS : "organises"
  USERS |o--o{ EVENT_REQUESTS : "coordinates"
  EVENT_REQUESTS ||--o{ EVENT_HISTORY_ENTRIES : "records"
  USERS |o--o{ EVENT_HISTORY_ENTRIES : "acts in"
  EVENT_REQUESTS ||--o{ EVENT_EQUIPMENT_LINES : "needs"
  EQUIPMENT_TYPES ||--o{ EVENT_EQUIPMENT_LINES : "requested as"
  USERS |o--o{ EVENT_EQUIPMENT_LINES : "reviews"
  USERS ||--o{ NOTIFICATIONS : "receives"
  EVENT_REQUESTS ||--o{ NOTIFICATIONS : "about"
  EVENT_REQUESTS ||--o{ REGISTRATIONS : "has"
  USERS ||--o{ REGISTRATIONS : "attends"
  USERS ||--o{ REVOKED_TOKENS : "logged out"

  CLIENT_ORGANISATIONS {
    int id PK
    string name
    string contact_email
  }
  USERS {
    int id PK
    string email UK
    string role
    int organisation_id FK
  }
  EVENT_REQUESTS {
    int id PK
    string reference UK
    int organiser_id FK
    int coordinator_id FK
    int organisation_id FK
    string status
    int registration_capacity
  }
  EVENT_HISTORY_ENTRIES {
    int id PK
    int event_request_id FK
    int actor_id FK
    string kind
    datetime occurred_at
  }
  EVENT_EQUIPMENT_LINES {
    int id PK
    int event_request_id FK
    int equipment_type_id FK
    int reviewed_by FK
    string status
    int quantity
  }
  NOTIFICATIONS {
    int id PK
    int recipient_id FK
    int event_request_id FK
    string kind
    datetime read_at
  }
  REGISTRATIONS {
    int id PK
    int event_request_id FK
    int attendee_id FK
    string status
  }
  REVOKED_TOKENS {
    int id PK
    string jti UK
    int user_id FK
    datetime expires_at
  }
  EQUIPMENT_TYPES {
    int id PK
  }
```

## 5b. Venues and bookings

```mermaid
erDiagram
  VENUES ||--o{ VENUE_OPENING_PERIODS : "opens"
  VENUES ||--o{ BOOKINGS : "booked"
  VENUES ||--o{ VENUE_BLOCKS : "blocked"
  VENUES ||--o{ VENUE_BOOKING_REQUESTS : "requested at"
  EVENT_REQUESTS ||--o{ VENUE_BOOKING_REQUESTS : "arranges"
  USERS ||--o{ VENUE_BOOKING_REQUESTS : "requests"
  BOOKINGS |o--o{ VENUE_BOOKING_REQUESTS : "backs"
  VENUE_BOOKING_REQUESTS |o--o{ VENUE_BOOKING_REQUESTS : "replaced by"
  VENUE_BOOKING_REQUESTS ||--o{ ALTERNATIVE_VENUE_FLAGS : "flagged by"
  VENUE_BLOCKS |o--o{ ALTERNATIVE_VENUE_FLAGS : "caused by"
  VENUE_BOOKING_REQUESTS ||--o{ REASSESSMENT_FLAGS : "reassess"

  VENUES {
    int id PK
    string name
    int capacity
    int setup_minutes
    int turnaround_minutes
  }
  VENUE_OPENING_PERIODS {
    int id PK
    int venue_id FK
    time open_time
    time close_time
  }
  BOOKINGS {
    int id PK
    int venue_id FK
    int event_id
    datetime start_time
    string status
    datetime hold_expires_at
  }
  VENUE_BLOCKS {
    int id PK
    int venue_id FK
    string category
    datetime start_time
  }
  VENUE_BOOKING_REQUESTS {
    int id PK
    int event_id FK
    int venue_id FK
    int booking_id FK
    int requested_by FK
    int replaces_request_id FK
    string status
  }
  ALTERNATIVE_VENUE_FLAGS {
    int id PK
    int booking_request_id FK
    int venue_block_id FK
    string category
  }
  REASSESSMENT_FLAGS {
    int id PK
    int booking_request_id FK
    string kind
  }
  EVENT_REQUESTS {
    int id PK
  }
  USERS {
    int id PK
  }
```

## 5c. Equipment

```mermaid
erDiagram
  VENUES |o--o{ EQUIPMENT_TYPES : "stored at"
  EQUIPMENT_TYPES ||--o{ EQUIPMENT_RESERVATIONS : "reserved as"
  EVENT_REQUESTS ||--o{ EQUIPMENT_RESERVATIONS : "holds"
  USERS ||--o{ EQUIPMENT_RESERVATIONS : "reserves"
  EQUIPMENT_TYPES ||--o{ EQUIPMENT_OUT_OF_SERVICE : "withdrawn"
  USERS ||--o{ EQUIPMENT_OUT_OF_SERVICE : "records"
  EQUIPMENT_TYPES ||--o{ EVENT_EQUIPMENT_LINES : "requested as"
  EVENT_REQUESTS ||--o{ EVENT_EQUIPMENT_LINES : "needs"

  EQUIPMENT_TYPES {
    int id PK
    string name
    int total_quantity
    int venue_id FK
  }
  EQUIPMENT_RESERVATIONS {
    int id PK
    int event_id FK
    int equipment_type_id FK
    int reserved_by FK
    int quantity
    datetime starts_at
    datetime ends_at
  }
  EQUIPMENT_OUT_OF_SERVICE {
    int id PK
    int equipment_type_id FK
    int recorded_by FK
    int resolved_by FK
    string reason
  }
  EVENT_EQUIPMENT_LINES {
    int id PK
    int event_request_id FK
    int equipment_type_id FK
    string status
    int quantity
  }
  VENUES {
    int id PK
  }
  EVENT_REQUESTS {
    int id PK
  }
  USERS {
    int id PK
  }
```

An event's equipment *line* (what the coordinator asked for) and its *reservation* (what Technical Support set
aside for a time window) are separate tables. A reservation reduces the quantity free for overlapping events.
