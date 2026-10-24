# ADR-0037: Equipment availability is calculated per event period; Technical Support reserve up to it under a row lock; out-of-service units are a read-only seam for SCRUM-47

- **Status:** Accepted; section 5 (the coordinator is notified of each reservation) superseded by [ADR-0102](0102-reserving-equipment-notifies-nobody.md): reserving notifies nobody, and the coordinator hears once, when the outcome is recorded
- **Date:** 2026-10-11
- **Story:** SCRUM-45 Check whether enough equipment is free; SCRUM-46 Reserve equipment
- **Extends:** [ADR-0014](0014-equipment-type-location-and-quantity.md): what is subtracted from `total_quantity`; [ADR-0015](0015-in-app-notifications.md) and [ADR-0018](0018-least-loaded-coordinator-and-event-history.md): a new notification kind and a new history kind; [ADR-0019](0019-event-equipment-lines.md) and [ADR-0022](0022-equipment-awaiting-action.md): what reserving does to an equipment line (nothing, for now), and who may read an event's equipment (as its lines, ADR-0019 and [ADR-0034](0034-coordinators-see-only-their-own-events.md)); [ADR-0025](0025-event-edits-significant-changes-and-history.md): history entries hidden from the organiser

## Context
SCRUM-45's ACs: ten projectors held and four reserved for an overlapping event leave six available (AC1); damaged or under-maintenance units are excluded (AC2); a shortfall is reported when more is requested than is available (AC3); availability is calculated for the event's exact start and end, not the whole day (AC4); two events that don't overlap both see the same equipment (AC5).

SCRUM-46's ACs: reserve up to the available quantity of a type for the event's period (AC1); a reservation reduces overlapping events' availability by the same amount (AC2); reserving more than is available is refused and the available quantity is shown (AC3); the reservation is linked to the event and visible on its record (AC4); the event's coordinator is notified (AC5).

Left open:
1. Whether availability is stored or calculated, and what "overlapping" means for equipment, which has no setup or turnaround time of its own.
2. Where damaged and under-maintenance units are recorded. SCRUM-47 owns setting an item's operational status, but SCRUM-45 AC2 already has to subtract those units.
3. How two Technical Support Staff reserving the same type at once are kept from reserving more than is free between them.
4. Which events can take reservations, what one reservation is, who sees it, and what it does to the event's equipment lines (ADR-0019 said "SCRUM-46 adds `reserved`").
5. Which ACs of related stories these two leave alone.

Neither story had Jira comments when read. The Atlassian MCP connection failed for most of the work, so the ACs were read once at the start and not re-read at the end.

## Decision

### 1. Availability is a calculation, never stored (SCRUM-45 AC1, AC2, AC4, AC5; SCRUM-46 AC2)
`equipment.services.available_quantity(equipment_type_id, starts_at, ends_at)` returns:

> `total_quantity` − units reserved for overlapping periods − unresolved out-of-service units, floored at 0.

- `total_quantity` is never written by reserving or by putting units out of service, as ADR-0014 says.
- **Reserved units:** `_reserved_quantity` sums `equipment_reservations.quantity` for the type, filtered by `_overlapping(starts_at, ends_at)`.
- **Out-of-service units:** `_out_of_service_quantity` sums the type's `equipment_out_of_service.quantity` where `resolved_at IS NULL` (section 2).
- **Floor at 0:** units can break after they were reserved, leaving more committed than held. The result is never negative.
- **Unknown type:** `404` "Equipment type not found." (through `get_equipment_type`).

**The overlap rule.** `_overlapping` is the one definition, used by every availability query:

```python
(EquipmentReservation.starts_at < ends_at) & (EquipmentReservation.ends_at > starts_at)
```

Both comparisons are strict, so a reservation ending exactly when another period starts doesn't overlap it (AC5). **Equipment has no setup or turnaround buffer.** Venues pad both events (ADR-0011), but a projector can go from one event straight to the next, so only the events' own periods count.

**The event's period** comes from the events module, which derives it: `get_event_equipment_need` combines `proposed_date` + `start_time` and `end_date` + `end_time`, each a wall-clock time in business time (ADR-0002), and turns them into UTC-aware instants with `app.common.clock.as_utc` (ADR-0009). An overnight event ends on its `end_date`. A missing date or time is `409 event_period_incomplete`, "The event has no complete date and times yet." (`EventPeriodIncompleteError`). The period is never guessed as the whole day (AC4). In practice the database's `ck_event_requests_details_unless_draft` means only a draft can lack them, and a draft is a `404` first.

**Per event** (SCRUM-45 AC3): `equipment_availability_for_event(reference)` returns one `EquipmentAvailability` per catalogue type, ordered by name:
- `equipment_type_id`, `equipment_type_name`
- `available` for the event's period
- `requested`: the quantity on the event's equipment line for that type (ADR-0019), 0 without a line
- `shortfall = max(requested − available, 0)`

An event that asks for nothing still sees every type. Each type costs two queries, which is accepted for readability while the catalogue is small.

### 2. The SCRUM-47 seam: `equipment_out_of_service`
**What exists now.** The model is `EquipmentOutOfService` in `app/modules/equipment/models.py`, table `equipment_out_of_service`, with these columns:

| Column | Type | Notes |
|---|---|---|
| `id` | integer primary key | |
| `equipment_type_id` | integer, not null | FK `equipment_types.id`, indexed (`ix_equipment_out_of_service_equipment_type_id`) |
| `quantity` | integer, not null | `ck_equipment_out_of_service_quantity_min`: `quantity >= 1` |
| `reason` | `OutOfServiceReason`, not null | Postgres enum `out_of_service_reason`, stored by value: `DAMAGED = "damaged"`, `UNDER_MAINTENANCE = "under_maintenance"` |
| `recorded_by` | integer, not null | FK `users.id`. Database level only: no ORM relationship across modules |
| `recorded_at` | `UTCDateTime`, not null | No server default: the writer sets it |
| `resolved_at` | `UTCDateTime`, nullable | `NULL` while the units are out of service |

There are no `created_at`/`updated_at` columns and no notes column.

**The rules as built:**
- **A row counts against availability while `resolved_at IS NULL`.** Once `resolved_at` is set, it no longer counts.
- **A row is not tied to a period.** An unresolved row reduces availability for *every* period, past and future, not only from `recorded_at` on.
- **A row counts units of a type, not individual items.** The catalogue has no per-item (serial number) table.

**Who reads it.** Only `available_quantity`, through the private helper `_out_of_service_quantity(equipment_type_id, session)`. Everything else gets the figure from there: `equipment_availability_for_event`, and `reserve_equipment`'s check.

**Who writes it.** Nothing in SCRUM-45/46: no route, schema, service or screen. Tests build rows directly with the `make_out_of_service` fixture in `backend/tests/equipment/conftest.py`.

**Migration `0021_add_equipment_reservations`** (revises `0019_add_review_kinds`) creates:
- enum type `out_of_service_reason`;
- table `equipment_out_of_service`, with its check constraint and index;
- table `equipment_reservations`, with `ck_equipment_reservations_quantity_min`, `ix_equipment_reservations_event_id` and `ix_equipment_reservations_type_period` (type, starts_at, ends_at);
- the value `equipment_reserved` in `event_history_entry_kind` and in `notification_kind`, added in an `autocommit_block` with `ADD VALUE IF NOT EXISTS`.

Its downgrade:
- deletes the notification and history rows of kind `equipment_reserved`;
- rebuilds both enum types without the value (lossy, like 0015's and 0019's);
- drops both tables and their indexes;
- drops `out_of_service_reason`.

**SCRUM-47 must build on top of this:**
- [ ] **The write path:** a route, schema and service that record units of a type as out of service (`quantity`, `reason`, `recorded_by` from `g.current_user_id`, `recorded_at` = now in UTC), and that resolve an entry by setting `resolved_at`. Partly resolving a row (some of its units back) needs a rule: resolve it and record a new row for the rest, or another design.
- [ ] **The audit of the change (its AC4).** `recorded_by` and `recorded_at` say who first recorded a row and when, but nothing records who resolved it, or any change after that. The audit trail or history of status changes is SCRUM-47's to design. It may add columns such as `resolved_by`.
- [ ] **Flagging the reservations that depend on newly affected items (its AC3).** Reservations are per type, by quantity (`EquipmentReservation.quantity`), not per item. So SCRUM-47 must decide how an out-of-service unit maps to the reservations it affects. One example: flag the overlapping reservations of that type whose total now exceeds `total_quantity − out-of-service`. **This is an open design question left to SCRUM-47.** Nothing here flags or releases a reservation when units break: availability just floors at 0.
- [ ] **The safety-check consequence (its AC5).**
- [ ] **Take the reserve guard's lock.** Whatever writes or resolves an `equipment_out_of_service` row must first lock the type's row with `_locked_equipment_type` (in `app/modules/equipment/services.py`, section 3), in the same transaction. Otherwise a reservation counting what is free can miss units that break at the same moment, and the two together commit more than is held. With the lock, the write waits for a reservation in progress (or the reservation for the write), so each counts the other.
- [ ] **Period and items.** Decide whether out-of-service rows become bound to a period (for example, maintenance from–to, so they reduce only overlapping periods) or tracked per item. Either one changes `_out_of_service_quantity`, the table (a migration) and the "every period" rule above.

**SCRUM-47 must not:**
- reduce `equipment_types.total_quantity` to take units out of service (ADR-0014);
- add a second availability formula. Change `_out_of_service_quantity` / `available_quantity` in `app/modules/equipment/services.py`, which every caller already goes through.

### 3. The over-commit guard (SCRUM-46 AC1, AC3)
`reserve_equipment` does these steps in one transaction:
1. Validates the body (`EquipmentUnitsSchema`).
2. Reads the event's need.
3. Locks the equipment type's row: `_locked_equipment_type`, which runs `SELECT … FROM equipment_types … FOR UPDATE` with `execution_options(populate_existing=True)`.
4. Recomputes `available_quantity` *under the lock*.
5. Inserts the reservation, flushes it, and adds the history entry.
6. Commits once.

A second reservation of the same type waits for the lock until the first commits. Under Postgres's default READ COMMITTED isolation, its counting queries then see the first one's units, so the two can't reserve more than was free between them. `populate_existing` stops an equipment type the session loaded earlier from being reused stale. Counting before locking would miss a reservation committed while this one waited. On a refusal the lock is held until the request's session is torn down (rolled back), as in the other services.

**Why not a database constraint.** "The sum of overlapping reservations is no more than what is held" is a sum over ranges, and depends on another table. A check or unique constraint can't express it. An exclusion constraint works on pairs, not on quantities. Locking one row per type serialises only reservations of that type.

**Limits, stated plainly:**
- SQLite ignores `FOR UPDATE`. The unit tests prove ordering, not blocking. `test_what_is_free_is_counted_after_the_equipment_type_is_locked` hooks `do_orm_execute`: when a statement compiled with the **Postgres** dialect selects from `equipment_types` `FOR UPDATE`, it inserts a competing reservation, and the test checks the competitor's units are counted. It goes red if the lock is removed or the count moves before it. `test_the_locked_read_replaces_what_the_session_already_holds` covers `populate_existing`.
- **That Postgres really blocks the second transaction is unverified here.** No database credentials were available. `flask db upgrade`, `flask db check` and the downgrade → upgrade replay of 0021 were not run either. CI runs them. `flask db heads` shows the single head `0021_add_equipment_reservations`.
- **Only reserving takes the lock today.** Nothing writes `equipment_out_of_service` yet (SCRUM-47 must take the lock when it does, section 2). SCRUM-27's `PATCH /api/equipment/types/<id>` can lower `total_quantity` without it, so a cut made while a reservation is being counted isn't seen by that reservation. That is a follow-up (Tickets to open).
- The guard relies on READ COMMITTED, Postgres's default, where each query sees what was committed before it started. Under a stricter isolation level the count after the lock could use a snapshot taken before it, so the guard would need rethinking.

### 4. The audit trail (beyond the Jira ACs)
**Neither SCRUM-45 nor SCRUM-46 asks for this.** The user asked for it.

Each reservation writes one event history entry of kind `EventHistoryKind.EQUIPMENT_RESERVED` (`"equipment_reserved"`), through `events.services.record_equipment_reserved`, which calls the existing `record_event_history`:
- `actor_id` is the reserving user.
- `details` = `{equipment_type_id, equipment_type_name, quantity, reservation_id}`.
- It is written in the same transaction as the reservation and never commits on its own, so the reservation and its entry are saved together or not at all.

Internal staff see the entry in `GET /api/events/requests/<reference>/history` with the actor's name (ADR-0025). It is **internal only**: `INTERNAL_ONLY_KINDS = {EQUIPMENT_RESERVED}`, which `_shown_to_organiser` checks, so organisers never see it.

### 5. The coordinator is notified (SCRUM-46 AC5)
*Superseded by [ADR-0102](0102-reserving-equipment-notifies-nobody.md):* AC5 now says reserving does not notify the coordinator by itself; they are notified once, when the outcome is recorded (SCRUM-48). `reserve_equipment` no longer calls `notify_coordinator_equipment_reserved`, which is gone, and the `equipment_reserved` notification kind stays only for notifications already sent. What follows is how it worked until then.

After the reservation's commit, `reserve_equipment` calls `events.services.notify_coordinator_equipment_reserved(event_id)`. The events module owns it, so equipment never writes notification rows or reads event models.
- **Who hears.** Only the event's assigned coordinator (ADR-0018), once per reservation, with kind `equipment_reserved` and the message "Equipment was reserved for an event.", linking to `/events/<reference>`.
- **Its own commit (ADR-0015).** If the notification can't be saved, it is rolled back and logged (`event_request_notification_failed … kind=equipment_reserved`). The reservation stands and the reply is still `201`.
- **Nobody assigned.** The reservation stands, nobody is notified, and `event_request_unassigned reference=…` is logged.

### 6. Other decisions
- **The event is named by its `EVR-` reference** in routes and services, with case and surrounding spaces ignored (ADR-0004), as everywhere else. The equipment module gets everything it needs from the events module, as an `EventEquipmentNeed` (`event_id`, `starts_at`, `ends_at`, `requested`, `accepts_reservations`), so it never imports event models. `get_event_equipment_need(reference)` finds any event but a draft, for reserving. `get_event_equipment_need_for_viewer(viewer_id, reference, viewer_role=...)` finds it only for a viewer who may read its equipment (below), for the two reads; it shares that check with `list_equipment_lines`. Each module imports the other's `services` *module* (`events_services` / `equipment_services`), not its names. That is what lets them import each other.
- **Reservations are additive rows.** Each call adds one `equipment_reservations` row, holding the event's period copied at reserving time. Several rows for one event and type add up. A type the event didn't request can be reserved too.
- **Which events take reservations:**
  * An event that is `completed`, `cancelled` or `rejected` (`EQUIPMENT_NOT_NEEDED_STATUSES`, the set ADR-0022 uses) is a `409 equipment_not_reservable`, with the message "Equipment can't be reserved for an event that is completed, cancelled or rejected." (`RESERVATIONS_CLOSED_MESSAGE`).
  * A draft or an unknown reference is `404` (ADR-0024).
  * An incomplete period is `409` (section 1).
  * Any other status may take reservations, including `submitted`. So may a `confirmed` event whose end has passed but that isn't yet marked completed.
- **Validation.** `EquipmentUnitsSchema` takes `equipment_type_id` and `quantity`, both whole numbers of at least 1, and nothing else. The two fields are `PositiveId` and `PositiveQuantity` from `app/common/fields.py`, which `EditEquipmentLineSchema` (ADR-0019) uses too, with the same messages. The events schemas therefore never import the equipment module's: modules meet only through their services. The checks run in this order:
  1. The body: `400`.
  2. The event: `404`, or `409` for an incomplete period.
  3. Whether it takes reservations: `409`.
  4. The type, under the lock: an unknown one is `400` on `equipment_type_id`, "Equipment type not found.".
  5. The quantity: more than is free is `400 validation_error`, with the message and `details.quantity` both "Only N available for this period." (AC3).
- **The reserver is shown by name, never by id** (`reserved_by`: their full name, or `null` once their account is gone), as the event record shows its actors (ADR-0025).
- **Reserving doesn't change `EventEquipmentLine.status`.** ADR-0019 expected a `reserved` value and ADR-0022 left partial reservations open. No AC needs it, and it would add a second irreversible Postgres enum value plus rules for partly reserved lines. So **SCRUM-38's awaiting-action list still shows lines that have been reserved.** That is a follow-up.
- **Reservations don't follow the event:**
  * When an event is later cancelled, rejected or completed, its reservations are **not released**.
  * When its date or times are later edited (SCRUM-33), a reservation's stored period is **not** updated.

  Both are follow-ups.

**Routes and roles:**

| Route | Roles | Reply |
|---|---|---|
| `GET /api/equipment/events/<reference>/availability` | `technical_support_staff` (any event but a draft), `event_coordinator` (an event assigned to them) | `200`, list of `{equipment_type_id, equipment_type_name, available, requested, shortfall}` |
| `POST /api/equipment/events/<reference>/reservations` | `technical_support_staff` | `201`, the reservation |
| `GET /api/equipment/events/<reference>/reservations` | `technical_support_staff` (any event but a draft), `event_coordinator` (an event assigned to them) | `200`, oldest first (`created_at`, then `id`), each `{id, equipment_type_id, equipment_type_name, quantity, starts_at, ends_at, reserved_by, created_at}`, times in business time with an offset (ADR-0009) |

**Both reads are scoped like the event's equipment lines** (`GET /api/events/requests/<reference>/equipment`, ADR-0019). Technical Support Staff read any event's equipment: arranging it is their job. An Event Coordinator reads only an event assigned to them; another coordinator's event, or one nobody is assigned, is the same `404` "Event request not found." as an unknown reference (ADR-0012), as the coordinator's event record is (ADR-0034). Venue Staff get `403`: equipment is Technical Support's and the coordinator's business, not theirs. The event history route lets any internal role read any event, but following it here would show every coordinator the equipment of events that aren't theirs.

**Frontend:**
- `/events/:reference/equipment` (`ROUTES.EVENT_EQUIPMENT`, `eventEquipmentPath`) shows the availability table and the reservations. It is guarded by `RequireRole(EQUIPMENT_READER_ROLES)` (Technical Support and coordinators, in `config/roles.ts`); the backend decides which events a coordinator may open.
- Only `EQUIPMENT_RESERVER_ROLES` (Technical Support) get a reserve form per row.
- The tables use a new shared `DataTable` in `components/ui`.
- The mock backend (`mocks/handlers/equipment.ts`) mirrors the routes, refusals and messages, including the read scoping: its open event is assigned to the mock coordinator, its closed one to nobody, and a `venueStaff` account is refused. It adds `technicalSupport` and `venueStaff` mock accounts.
- After a reservation, refused or not, the page reads the event's availability and reservations again, so a refusal like "Only N available" leaves the table showing the backend's current numbers.
- Nothing links to the page yet: there is no event record page in the frontend.

### 7. Deferred, with their owners
- **Recording a review outcome:** SCRUM-48.
- **The operational-status write path, its audit, and flagging the reservations that depend on affected items:** SCRUM-47 (section 2).
- **Gating confirmation on the equipment being reserved:** SCRUM-49.

## Consequences
- Availability always reflects the current rows. Nothing has to be kept in step, and SCRUM-47 changes availability just by writing `equipment_out_of_service` rows.
- Reserving serialises per equipment type. Reservations of different types never wait for each other.
- An event can hold reservations for types it never requested, and its record shows them.
- Reservations of cancelled events keep their units until a release story exists. Reservations of events whose times change keep the old period.
- SCRUM-31's decision lock (`_has_arrangements`, ADR-0028) counts equipment lines, not reservations. A reservation made without a line doesn't lock the decision.
- **Merging with the sibling migrations.** Migrations 0020 (SCRUM-42) and 0022 (SCRUM-95), on their own branches, also revise `0019_add_review_kinds` and add `notification_kind` values; 0020 also adds `event_history_entry_kind` values. Whichever of the three lands later must:
  1. set its `down_revision` to the head it lands on, so there is one head (`flask db heads`);
  2. add the values the earlier ones added to `PREVIOUS_HISTORY_KIND_VALUES` / `PREVIOUS_NOTIFICATION_KIND_VALUES` in its `_rebuild_enum` downgrade, or downgrading it drops a sibling's enum value along with its own;
  3. for 0021, point `HISTORY_MIGRATION_BELOW` / `NOTIFICATION_MIGRATION_BELOW` in `backend/tests/events/test_equipment_reservations_migration.py` at the migration now below it, which checks step 2.

## Tickets to open
- Release an event's reservations when it is cancelled or rejected (and decide what completion does).
- Move a reservation's period when the event's date or times are edited, or flag it.
- Clear or partly resolve an `EventEquipmentLine` once it is reserved, so SCRUM-38's list drops it (ADR-0019, ADR-0022).
- Decide per-item versus per-type reservations together with SCRUM-47's out-of-service flagging.
- Make SCRUM-27's `PATCH /api/equipment/types/<id>` take `_locked_equipment_type` when it changes `total_quantity`, so lowering it serialises with reserving (section 3).
- Frontend integration (contract) tests for the three equipment routes in `frontend/src/integration/`. They need a seeded Technical Support account and a submitted event.
- Link the equipment page from the event record page once one exists (SCRUM-24/30 UI).
- Tidy-ups:
  * Move `formatDate` from `features/catalogue` to `lib/`.
  * Extract an e2e `signInAs` helper: `e2e/equipment.spec.ts` repeats `catalogue.spec.ts`'s session seeding.
  * Add an `ends_at > starts_at` check to `equipment_reservations`.
- Test fixtures moved into `backend/tests/conftest.py` (`make_event_request`, `saved_event_request`, `make_equipment_line`, `microphone`, `notifications_of`) may conflict with sibling branches that edit `tests/events/conftest.py`.

## Revisit when
- SCRUM-47 lands: out-of-service rows gain a writer and maybe a period or item identity.
- SCRUM-49 lands: confirmation checks the reservations.
- Postgres is run with concurrent reservations: confirm the lock blocks as described, or switch to an advisory lock.
- The catalogue grows enough that two queries per type for availability is slow: sum reservations and out-of-service units for all types in one query each.
