# UML sequence diagrams

Routes are the real ones in `backend/app/modules/*/routes.py`. Every call goes from the Web App to the Backend
API with a Bearer JWT. The API writes to PostgreSQL and also writes in-app notifications there.

## 7a. From request to approval

```mermaid
sequenceDiagram
  autonumber
  actor Org as Event Organiser
  actor Lead as Coordinator Lead
  actor Coord as Event Coordinator
  participant Web as Web App
  participant API as Backend API
  participant DB as PostgreSQL

  Org->>Web: Fill in the request
  Web->>API: POST /api/events/requests
  API->>DB: Insert event request (submitted) and history entry
  API->>DB: Notify every Lead (request_queued_for_lead)
  API-->>Web: 201 reference

  Lead->>Web: Open the unassigned queue
  Web->>API: GET /api/events/requests/unassigned
  Lead->>Web: Pick a coordinator
  Web->>API: POST /api/events/requests/:reference/coordinator
  API->>DB: Set coordinator, add history, notify organiser and coordinator

  Coord->>Web: Open the request
  Web->>API: POST /api/events/requests/:reference/review
  API->>DB: Status becomes under_review

  opt Information is missing
    Coord->>Web: Ask for clarification
    Web->>API: POST /api/events/requests/:reference/request-clarification
    API->>DB: Status becomes awaiting_clarification, notify organiser
    Org->>Web: Answer
    Web->>API: POST /api/events/requests/:reference/resubmit
    API->>DB: Status back to under_review, notify coordinator
  end

  Coord->>Web: Approve
  Web->>API: POST /api/events/requests/:reference/decide
  API->>DB: Status becomes approved, notify organiser
```

## 7b. Venue booking and equipment

```mermaid
sequenceDiagram
  autonumber
  actor Coord as Event Coordinator
  actor VS as Venue Staff
  actor Tech as Technical Support Staff
  participant API as Backend API
  participant DB as PostgreSQL

  Coord->>API: POST /api/venues/search
  Coord->>API: POST /api/venues/:id/suitability
  API-->>Coord: Suitable, or what is missing
  Coord->>API: POST /api/venues/events/:reference/booking-requests
  API->>DB: Insert booking request (pending)
  API->>DB: Notify every Venue Staff user

  alt Venue Staff approve
    VS->>API: POST /api/venues/booking-requests/:id/decision
    API->>DB: Request approved, booking confirmed
    API->>DB: Overlapping pending requests become conflicting
    API->>DB: Notify the coordinator
  else Venue Staff hold first
    VS->>API: POST /api/venues/booking-requests/:id/hold
    API->>DB: Request on_hold, tentative booking with an expiry
  end

  Coord->>API: POST /api/events/requests/:reference/equipment
  API->>DB: Add equipment line (requested), notify Technical Support
  Tech->>API: GET /api/equipment/events/:reference/availability
  Tech->>API: POST /api/equipment/events/:reference/reservations
  API->>DB: Reservation reduces the quantity free for overlapping events
  Tech->>API: POST /api/events/requests/:reference/equipment/:line_id/outcome
  API->>DB: Line becomes fulfilled, partially fulfilled or unavailable
  API->>DB: Notify the coordinator
```

## 7c. Safety check and confirmation

```mermaid
sequenceDiagram
  autonumber
  actor Coord as Event Coordinator
  actor SO as Safety Officer
  actor Org as Event Organiser
  participant API as Backend API
  participant DB as PostgreSQL

  Coord->>API: POST /api/events/requests/:reference/safety-review
  API->>DB: Status becomes safety_review, notify Safety Officers
  SO->>API: GET /api/events/requests/awaiting-safety-review
  SO->>API: POST /api/events/requests/:reference/safety-outcome

  alt Approved
    API->>DB: Record approval, notify coordinator
    Coord->>API: POST /api/events/requests/:reference/confirm
    API->>DB: Check approvals, venue arrangements and equipment outcomes
    API->>DB: Status becomes confirmed, notify organiser
  else Rejected or changes requested
    API->>DB: Status returns to approved, notify coordinator
  end
```

## 7d. Rejecting an event during planning releases its arrangements

```mermaid
sequenceDiagram
  autonumber
  actor Coord as Event Coordinator
  participant Ev as events module
  participant Ve as venue module
  participant Eq as equipment module
  participant DB as PostgreSQL
  actor VS as Venue Staff

  Coord->>Ev: POST /api/events/requests/:reference/reject with a reason
  Ev->>Ev: Allow only approved or safety_review
  Ev->>DB: Status becomes rejected, add decision entry
  Ev->>Ve: release_event_arrangements
  Ve->>DB: Withdraw pending, conflicting, rejected or expired requests
  Ve->>DB: Release approved and on_hold requests, cancel their bookings
  Ev->>Eq: release_event_reservations
  Eq->>DB: Return reserved equipment
  Ev->>DB: Notify the organiser with the reason
  Ev->>Ve: tell_venue_staff_of_releases
  Ve-->>VS: One venue_booking_released notice per release
```

## 7e. Hourly hold expiry

```mermaid
sequenceDiagram
  autonumber
  participant GHA as Hourly scheduler
  participant CLI as flask expire-holds
  participant Ve as venue services
  participant DB as PostgreSQL
  actor Coord as Event Coordinator

  GHA->>GHA: Cron at minute 7 of every hour
  alt No DATABASE_URL secret
    GHA-->>GHA: Skip with a notice (no deployed database yet)
  else Secret present
    GHA->>CLI: Run the command
    CLI->>Ve: expire_holds
    Ve->>DB: Holds past their expiry become expired, booking freed
    Ve->>DB: Notify coordinator (venue_hold_expired)
    CLI->>Ve: send_hold_expiry_warnings
    Ve->>DB: Notify coordinator 24 hours ahead (venue_hold_expiring)
    Note over DB,Coord: The coordinator reads the notices in the Web App
  end
```
