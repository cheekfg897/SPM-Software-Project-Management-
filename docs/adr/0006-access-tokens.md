# ADR-0006: Log in with a 1-hour JWT access token, no refresh token yet

- **Status:** Accepted; the "no real logout" and "no session state" consequences superseded by [ADR-0110](0110-logout-revokes-the-access-token.md) (SCRUM-89: logging out revokes that token through a `jti` blocklist, the Product Owner's choice of 25 Oct)
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
- ~~The server keeps no session state, so any instance can check any token.~~ Superseded by
  [ADR-0110](0110-logout-revokes-the-access-token.md): every request with a token now reads the
  logout blocklist, a table every instance shares.
- ~~A token can't be revoked before it expires, so there is no real logout (SCRUM-6 AC4).~~
  Superseded by [ADR-0110](0110-logout-revokes-the-access-token.md): `POST /api/auth/logout`
  revokes the token it is sent with (SCRUM-89, the Product Owner's option 2 of 25 Oct).
- A role change only takes effect when the user's current token expires.

## Revisit when
- Refresh tokens are added, or a role change needs to take effect at once (see ADR-0110's
  "Revisit when").
