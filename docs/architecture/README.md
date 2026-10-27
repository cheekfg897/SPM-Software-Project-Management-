# ConnectSphere architecture

C4 and UML diagrams of ConnectSphere as it stands on `main` and in Jira (statuses read 27 Oct 2026).
All diagrams are Mermaid, so GitHub renders them directly from the `.md` files. PNG copies are in `rendered/` for slides and the submission zip.

| File | Contents |
|---|---|
| `01-c4-context.md` | C4 level 1: how users interact with the system |
| `02-c4-containers.md` | C4 level 2: web app, backend API, database, hold-expiry job |
| `03-c4-components.md` | C4 level 3: module dependencies, and layering inside the venue module |
| `04-uml-class-diagrams.md` | UML classes: event planning domain, venue and equipment domain |
| `05-er-diagram.md` | Database tables, split into three views |
| `06-uml-state-diagrams.md` | Event request and venue booking request lifecycles |
| `07-uml-sequence-diagrams.md` | Request to approval, venue and equipment, safety check, rejection, hold expiry |

## Built vs planned (Jira, 27 Oct)
- **Planned, no code on main yet:** change requests (SCRUM-56, 57), reassessment (58-60), cancellation (61, so `cancelled` has no transition), notifications for changes (62), alternative suggestion (70), pre-filled venue search (90), return to planning after the safety check (99).
- **Drawn dashed or grey** in the diagrams where they appear.
- **Not drawn:** BEYOND stories (SCRUM-71 to 83, 109).

## Caveats
- Notifications are in-app only.
- The hold-expiry job is wired but inactive without `DATABASE_URL`.
- There are circular imports between modules; `events` is the hub.
- `Booking.event_id` has no foreign key.
- C4 is drawn as styled flowcharts, because Mermaid's native C4 syntax lays out badly.
