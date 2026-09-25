# ADR-0007: A refused request is "recorded" as a structured log line

- **Status:** Accepted
- **Date:** 2026-09-25 (recorded from the Sprint 1 `STORIES.md`; the code has followed it since then)
- **Story:** SCRUM-21 Enforce permissions for every role (AC5: "the request is refused and the
  attempt is recorded")

## Context
The AC says a refused attempt is recorded, but not where, for how long, or who reads it.

## Decision
- Every refused request (`401` for a missing, invalid or expired token; `403` for a role that
  isn't allowed) writes one `WARNING` line to the `connectsphere.authz` logger.
- The line holds the reason, the role attempted, the endpoint, the HTTP method, the path and a
  UTC timestamp, as `key=value` pairs.
- Nothing is stored in the database.

## Consequences
- Cheap, and it can't fail the request.
- Records last only as long as the logs are kept, and can't be queried from the app.
- The dedicated logger name lets these lines be routed elsewhere later without code changes.

## Revisit when
- An auditability story needs records that are retained, queryable or shown in the app. Then
  add an audit table and supersede this ADR.
