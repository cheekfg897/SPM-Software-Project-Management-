# ADR-0004: Event request reference is a random code like `EVR-XXXXXXXX`

- **Status:** Accepted
- **Date:** 2026-09-15
- **Story:** SCRUM-19 Submit an event request (AC5: "a reference it can be identified by")

## Context
Each request needs an ID that organisers and staff can quote in emails, calls, and on screen. Options considered:

| Option | Example | Problems |
|---|---|---|
| Database id | `42` | Guessable, so other people's requests can be probed. Reveals how many requests exist. Unknown until the row is saved, and the mocked unit tests never save it. |
| Formatted sequence | `EVR-2026-0042` | Needs a DB sequence or counter. Guessable. Same testing problem. |
| Random code | `EVR-7K2QX9AB` | Not sequential |

## Decision
- The reference is `EVR-` followed by **8 characters** chosen with `secrets` from a 31-character alphabet with no look-alikes: `23456789ABCDEFGHJKMNPQRSTUVWXYZ` (no `0 O 1 I L`).
- It's created in the service layer, stored in a `reference` column with a **unique index**, and never changed afterwards.
- If saving fails because the reference already exists, roll back, generate a new one and retry, up to 3 attempts. After that, raise an error.
- The generator can be swapped in tests.
- Lists are sorted by `created_at`, not by reference.
- The internal integer `id` stays the primary key.

## Consequences
- About 8.5 × 10¹¹ combinations, so collisions are very unlikely and the retry is only a safety net.
- Not guessable, but **it is not an access control**. Every lookup must still check ownership or role.
- Easy to read out over the phone. Lookups should ignore case and surrounding spaces.
- The prefix makes the type clear if other entities get references later, such as `BKG-` for bookings.

## Revisit when
- The business wants sequential or yearly references for reporting or audits.
- An external system sets the reference format.
