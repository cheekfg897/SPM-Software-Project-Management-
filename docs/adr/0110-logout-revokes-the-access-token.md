# ADR-0110: Logging out revokes that access token on the server, through a `jti` blocklist

- **Status:** Accepted; server-side revocation with a `jti` blocklist is the Product Owner's choice of 25 Oct (SCRUM-89 option 2, answer 1); decisions 2 to 7 are defaults to review
- **Date:** 2026-10-26
- **Story:** SCRUM-89 No logout; access tokens can't be revoked (SCRUM-6 Log in to the system, AC4: "Can log out, after which protected pages are no longer reachable")
- **Supersedes:** [ADR-0006](0006-access-tokens.md)'s "no real logout" and its "the server keeps no session state" consequence. The rest of ADR-0006 (a 1-hour JWT access token, no refresh token) stands.

## Context
Until now, logging out only made the web app forget its token. The token itself stayed valid until it expired (an hour by default), so anyone holding a copy could still reach every protected page. SCRUM-89 offered three ways to close that gap; on 25 Oct the Product Owner chose option 2: keep each logged-out token's `jti` in a blocklist table and check it through Flask-JWT-Extended's `token_in_blocklist_loader`. The story doesn't say which tokens a logout revokes, what the web app does when the call fails, or how long the blocklist keeps a row.

## Decision
1. **`POST /api/auth/logout` revokes the token it is sent with, and answers `204` with no body.** Any signed-in user may call it (`@requires_auth`). The token's `jti`, its user and its expiry go into a new `revoked_tokens` table (migration 0048), with the `jti` unique and `expires_at` indexed for the clean-up (decision 5). Without a token, or with one that is already invalid, the call gets the usual `401`.
2. **Default to review: only that token is revoked.** Logging out ends this browser's session; the user's other devices stay signed in until their tokens expire. Revoking every token of a user on a password change, a role change or deactivation is out of scope: none of those features exist yet.
3. **A revoked token is refused like an expired one.** The blocklist check runs inside `verify_jwt_in_request`, which `@requires_auth`, `@requires_role` and `@optional_auth` all call, so every protected route answers `401` with "Missing, invalid or expired token.", and the refusal is logged as an `authz_failure` (ADR-0007) with `detail=Token has been revoked`. On the public catalogue a revoked token is read as a visitor, as an expired one is. Flask-JWT-Extended's own `revoked_token_loader` gives the same body, for any route that uses `@jwt_required()` directly.
4. **Default to review: the web app signs out locally whatever the call returns.** It sends the logout first, while the session still holds the token, then forgets the session and goes to the front page as before. If the call fails (offline, or the token had already expired, which the backend refuses with a `401`), the user is signed out on this device all the same. Another tab using the same token is signed out by its next request's `401`; there is no live cross-tab sign-out.
5. **Default to review: rows are deleted once the token has expired, on each logout.** A row is only needed until `expires_at`, because after that the token is refused as expired anyway. Each logout deletes the rows whose `expires_at` is at or before now, in the same commit that adds its own row, so the table holds at most the logouts of the last hour. There is no scheduled job. This relies on Flask-JWT-Extended's default of no decode leeway; if `JWT_DECODE_LEEWAY` is ever set, the clean-up must keep rows that much longer.
6. **Default to review: one log line per logout.** `logout user_id=<id> jti=<jti>` goes to the `connectsphere.authz` logger at `INFO`, beside the refused-request lines of ADR-0007. The token itself is never logged. So that the line is seen, the app factory now sends the `connectsphere.*` loggers' `INFO` lines to the console, with one handler however many apps are built; before, only their warnings reached it, through Python's last-resort handler.
7. **Two logouts racing with the same token are not an error.** If the other one saved the `jti` first, the unique constraint refuses the second row; the service rolls back and returns, since the token is revoked either way.

## Consequences
- SCRUM-6 AC4 holds on the server: after logging out, the token can't reach a protected page from anywhere.
- The server now keeps state for tokens: every request with a token reads `revoked_tokens` once, by its unique `jti`. Any instance can still check any token, since the table is shared.
- The unit suite's in-memory database always has the `revoked_tokens` table (an autouse fixture in `tests/conftest.py`), because every request with a token now reads it.
- The mock backend revokes the token on logout too, and every mock handler that reads the caller then refuses it. Mock tokens are one per account, so logging in again in the mock issues that token afresh.

## Revisit when
- Password change, role change or account deactivation is built: revoke all of that user's tokens then, as ADR-0006's "a role change only takes effect when the token expires" still says.
- Refresh tokens are added: revoke the refresh token on logout too.
- The team wants "log out everywhere", or a live sign-out across tabs.
