# ADR-0006: Log in with a 1-hour JWT access token, no refresh token yet

- **Status:** Accepted
- **Date:** 2026-09-25 (recorded from the Sprint 1 `STORIES.md`; the code has followed it since then)
- **Story:** SCRUM-6 Log in to the system

## Context
The story says users log in with email and password, but not how a logged-in session is carried
between requests or how long it lasts.

## Decision
- A successful login returns a **JWT access token**, sent as `Authorization: Bearer <token>`.
- The token carries the user's id as its subject and their role in a `role` claim, which the
  permission decorators read.
- It expires after `JWT_ACCESS_TOKEN_EXPIRES_SECONDS`, **1 hour** by default.
- There are **no refresh tokens** yet; when the token expires, the user logs in again.

## Consequences
- The server keeps no session state, so any instance can check any token.
- A token can't be revoked before it expires, so there is no real logout (SCRUM-6 AC4). That gap
  is tracked as SCRUM-89.
- A role change only takes effect when the user's current token expires.

## Revisit when
- SCRUM-89 (logout and revocation) is designed; it will likely supersede this ADR.
