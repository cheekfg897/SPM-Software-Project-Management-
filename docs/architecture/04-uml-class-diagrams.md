# UML class diagrams: domain model

Built from the SQLAlchemy models in `backend/app/modules/*/models.py`. Attributes are the mapped columns.
The models have no behaviour of their own: the rules live in each module's `services.py`, so the boxes show
data only. `?` means the column can be null.

## 4a. Event planning, people and registration

```mermaid
classDiagram
  direction LR

  class User {
    +int id
    +string email
    +string full_name
    +Role role
    +int organisation_id?
  }
  class ClientOrganisation {
    +int id
    +string name
    +string contact_name
    +string contact_email
    +string contact_phone?
  }
  class EventRequest {
    +int id
    +string reference
    +int organiser_id
    +int coordinator_id?
    +int organisation_id?
    +string name
    +date proposed_date?
    +date end_date?
    +time start_time?
    +time end_time?
    +int expected_attendance?
    +bool registration_required
    +bool registration_enabled
    +int registration_capacity?
    +datetime withdrawal_cut_off?
    +EventRequestStatus status
  }
  class EventHistoryEntry {
    +int id
    +EventHistoryKind kind
    +int actor_id?
    +dict details
    +datetime occurred_at
  }
  class EventEquipmentLine {
    +int id
    +int quantity
    +EquipmentLineStatus status
    +int provided_quantity?
    +string outcome_note?
    +int reviewed_by?
  }
  class Registration {
    +int id
    +RegistrationStatus status
    +datetime registered_at
    +datetime withdrawn_at?
  }
  class Notification {
    +int id
    +string event_reference
    +NotificationKind kind
    +datetime created_at
    +datetime read_at?
    +string detail?
  }
  class EquipmentType {
    +int id
    +string name
    +int total_quantity
  }
  class RevokedToken {
    +int id
    +string jti
    +datetime expires_at
  }

  ClientOrganisation "0..1" <-- "0..*" User : belongs to
  User "1" <-- "0..*" RevokedToken : logged out
  User "1" <-- "0..*" EventRequest : organiser
  User "0..1" <-- "0..*" EventRequest : coordinator
  ClientOrganisation "0..1" <-- "0..*" EventRequest : client of
  EventRequest "1" *-- "0..*" EventHistoryEntry : history
  EventRequest "1" *-- "0..*" EventEquipmentLine : equipment lines
  EquipmentType "1" <-- "0..*" EventEquipmentLine : requested as
  EventRequest "1" <-- "0..*" Registration : for
  User "1" <-- "0..*" Registration : attendee
  User "1" <-- "0..*" Notification : recipient
  EventRequest "1" <-- "0..*" Notification : about

```

**Enumerations used above**

| Enum | Values |
|---|---|
| `Role` | event_organiser, attendee, event_coordinator, event_coordinator_lead, venue_staff, technical_support_staff, safety_officer |
| `EventRequestStatus` | draft, submitted, under_review, awaiting_clarification, approved, safety_review, confirmed, completed, cancelled, rejected |
| `EquipmentLineStatus` | requested, fulfilled, partially_fulfilled, unavailable |
| `RegistrationStatus` | registered, withdrawn |

`EventHistoryKind` (23 kinds) and `NotificationKind` (30 kinds) are enumerations too. They are left off the
diagram because their value lists are long. See `events/models.py` and `notifications/models.py`.

## 4b. Venues, bookings and equipment

```mermaid
classDiagram
  direction LR

  class Venue {
    +int id
    +string name
    +string location
    +int capacity
    +string facilities
    +string accessibility_features
    +string supported_layouts
    +int setup_minutes
    +int turnaround_minutes
    +bool is_active
  }
  class VenueOpeningPeriod {
    +int open_day
    +time open_time
    +int close_day
    +time close_time
  }
  class Booking {
    +int id
    +int event_id?
    +datetime start_time
    +datetime end_time
    +BookingStatus status
    +datetime hold_expires_at?
    +datetime hold_warning_sent_at?
  }
  class VenueBlock {
    +int id
    +datetime start_time
    +datetime end_time
    +UnavailabilityCategory category
    +string reason
  }
  class VenueBookingRequest {
    +int id
    +int event_id
    +datetime starts_at
    +datetime ends_at
    +string purpose
    +int expected_occupancy
    +string required_layout?
    +string decision_reason?
    +BookingRequestStatus status
    +PreparationStatus preparation_status
    +int requested_by
    +int replaces_request_id?
  }
  class AlternativeVenueFlag {
    +int id
    +UnavailabilityCategory category
    +string reason
    +datetime starts_at
    +datetime ends_at?
  }
  class ReassessmentFlag {
    +int id
    +ReassessmentFlagKind kind
    +string reason
  }
  class EquipmentType {
    +int id
    +string name
    +int total_quantity
    +string store_name?
  }
  class EquipmentReservation {
    +int id
    +int event_id
    +int quantity
    +datetime starts_at
    +datetime ends_at
    +bool needs_attention
    +PreparationStatus preparation_status
    +int reserved_by
  }
  class EquipmentOutOfService {
    +int id
    +int quantity
    +OutOfServiceReason reason
    +int recorded_by
    +datetime resolved_at?
  }
  class EventRequest {
    <<from events module>>
  }

  Venue "1" *-- "0..*" VenueOpeningPeriod : opening hours
  Venue "1" <-- "0..*" Booking : booked at
  Venue "1" <-- "0..*" VenueBlock : blocked
  Venue "1" <-- "0..*" VenueBookingRequest : requested at
  EventRequest "1" <-- "0..*" VenueBookingRequest : arrangements
  Booking "0..1" <-- "0..*" VenueBookingRequest : backed by
  VenueBookingRequest "0..1" <-- "0..*" VenueBookingRequest : replaces
  VenueBookingRequest "1" *-- "0..*" AlternativeVenueFlag : flags
  VenueBlock "0..1" <-- "0..*" AlternativeVenueFlag : caused by
  VenueBookingRequest "1" *-- "0..*" ReassessmentFlag : reassess
  Venue "0..1" <-- "0..*" EquipmentType : stored at
  EquipmentType "1" <-- "0..*" EquipmentReservation : reserved as
  EventRequest "1" <-- "0..*" EquipmentReservation : reserves
  EquipmentType "1" *-- "0..*" EquipmentOutOfService : out of service

```

**Enumerations used above**

| Enum | Values |
|---|---|
| `BookingRequestStatus` | pending, on_hold, approved, rejected, conflicting, withdrawn, expired, released |
| `BookingStatus` | tentative, confirmed, conflicting, cancelled |
| `PreparationStatus` | not_started, in_progress, ready |

`UnavailabilityCategory`, `ReassessmentFlagKind` and `OutOfServiceReason` are also enums. See `venue/models.py` and
`equipment/models.py` for their values.

`Booking.event_id` is a plain integer with no foreign key, so a booking is tied to its event only by
convention. The request-to-booking link (`booking_id`) is set only for holds and bookings a hold turned into.
