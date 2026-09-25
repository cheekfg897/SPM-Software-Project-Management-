# ADR-0014: An equipment type is one uniquely named record, held at one venue or one named store

- **Status:** Accepted
- **Date:** 2026-09-25
- **Story:** SCRUM-27 Maintain the equipment catalogue

## Context
SCRUM-27 AC1 says Technical Support Staff *"can create and edit an equipment type recording name, description, total quantity held and the venue or store it is located at"*. It doesn't say how "the venue or store" is recorded. Venues are already catalogued (SCRUM-25); stores aren't catalogued anywhere. The story's aim is one accurate record to calculate availability from instead of several spreadsheets, and SCRUM-45 (equipment availability) will calculate from it.

Options for the location:
- **A. One free-text location.** Simple, but "Main Hall" and "main hall " become two places, and there's nothing to join a venue on.
- **B. A foreign key to venues only.** Can't record equipment kept in a store, which the AC names.
- **C. A venue foreign key or a free-text store name, exactly one.**

## Decision
- **Location is option C.** An equipment type has either `venue_id` or `store_name`, never both and never neither. A check constraint (`ck_equipment_types_one_location`) enforces it in the database, and the schema rejects the other cases with a 400 whose details are on `venue_id`.
- **The venue** must exist in the catalogue, checked through the venue module's `get_venue`. A deactivated venue still counts: equipment can stay where it is.
- **Updates replace the location as a whole**, as opening hours do (ADR-0008). A `PATCH` that sends `venue_id` or `store_name` moves the equipment there and clears the other; a `PATCH` that sends neither leaves the location alone.
- **Names are unique** (`uq_equipment_types_name`); a duplicate is a 409. Two "Projector" rows would make "ten projectors held" ambiguous. The match is exact, so "Projector" and "projector" are different names.
- **`total_quantity` is the number of units held**: a whole number, 0 or more, with no upper limit. It is never reduced by reservations or damage. SCRUM-45 subtracts reservations when it calculates availability, and SCRUM-47 records out-of-service units alongside. Zero is allowed so a retired type keeps its record for past events that listed it.
- **Stores aren't catalogued.** A store is just the name on the equipment record.

## Consequences
- The equipment module depends only on the venue module's `services.get_venue`, never on its models.
- Responses carry `venue_id`, not the venue's name; a client that wants the name fetches the venue.
- Deactivating a venue doesn't touch the equipment kept there.
- Every location error, whichever field caused it, is reported on `venue_id`.

## Revisit when
- Stores need to be listed, renamed in one place or given details: they become a table, and `store_name` a foreign key.
- SCRUM-47 needs a record per unit: `total_quantity` may then be derived from those records.
- One type has to be split across several places: location moves to a (type, place, quantity) table.
