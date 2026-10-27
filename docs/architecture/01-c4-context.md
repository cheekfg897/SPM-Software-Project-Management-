# C4 level 1: system context

Who uses ConnectSphere, and how they interact with it. Roles come from the `Role` enum in
`backend/app/modules/auth/permissions.py`. Notifications are in-app only, so there is no email or SMS
system on this diagram. Only people appear here; delivery tooling is left out.

The C4 diagrams in this folder are drawn as Mermaid flowcharts that follow C4 conventions (person, system,
container and component boxes, with the technology in square brackets). Mermaid's own `C4Context` syntax is
experimental and lays out poorly, so it is not used.

```mermaid
flowchart LR
  classDef person fill:#08427b,stroke:#052e56,color:#ffffff
  classDef ext fill:#6b6b6b,stroke:#4a4a4a,color:#ffffff
  classDef system fill:#1168bd,stroke:#0b4884,color:#ffffff

  organiser["<b>Event Organiser</b><br/>[Person, external]<br/>Requests events and answers<br/>clarifications"]:::ext
  attendee["<b>Attendee</b><br/>[Person, external]<br/>Registers for confirmed events"]:::ext

  coordinator["<b>Event Coordinator</b><br/>[Person]<br/>Plans an assigned event"]:::person
  lead["<b>Event Coordinator Lead</b><br/>[Person]<br/>Assigns new requests"]:::person
  venuestaff["<b>Venue Staff</b><br/>[Person]<br/>Decides booking requests"]:::person
  tech["<b>Technical Support Staff</b><br/>[Person]<br/>Reserves equipment"]:::person
  safety["<b>Safety Officer</b><br/>[Person]<br/>Records the safety check"]:::person

  cs["<b>ConnectSphere</b><br/>[Software system]<br/>Event requests, venue booking,<br/>equipment reservation, registration<br/>and in-app notifications"]:::system


  organiser -->|"submits requests,<br/>answers clarifications"| cs
  attendee -->|"registers, withdraws"| cs
  coordinator -->|"reviews, books,<br/>confirms"| cs
  lead -->|"assigns coordinators"| cs
  venuestaff -->|"approves, rejects, holds"| cs
  tech -->|"reserves, records outcomes"| cs
  safety -->|"records outcome"| cs
```
