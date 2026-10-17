# ADR-0057: The front page is for visitors; a signed-in user who opens it, or clicks the logo, goes to their role's home

- **Status:** Accepted; sending signed-in users away from the front page is a default to review
- **Date:** 2026-10-17
- **Story:** SCRUM-6 Log in to the system (AC3, AC4)
- **Extends:** ADR-0044 (an Attendee's home is their events)

## Context
SCRUM-6 AC3: a user "is taken to the landing view for their role after a successful login".
`homeFor(role)` (`features/auth/roleHome.ts`) gives each role's home, and logging in goes there.
But the site's front page (`/`) and the logo, which links to it, showed a signed-in user the
visitors' page: the black-hole hero, "Create an account" and the header's Sign up button. The
AC does not say what `/` shows someone already signed in.

## Decision
1. **`/` shows the landing page only to visitors.** The route wraps `LandingPage` in the existing
   `SignedOutOnly`, which the log-in and sign-up pages already use, so a signed-in user is sent
   to `homeFor(role)`, replacing `/` in the history so Back doesn't bounce them there again.
2. **The logo keeps linking to `/`.** It lives in `components/layout`, which may not import a
   feature, and through decision 1 the click lands on the role's home anyway.
3. **Logging out forgets the session first, then leaves.** It used to leave for `/` first, so a
   page only signed-in users may see wouldn't send them to log in; with decision 1, arriving at
   `/` still signed in sent them straight back home, and then to log in. Now the session is
   cleared in one synchronous render (`flushSync`), and the navigation to `/` that follows
   replaces the log-in redirect the protected page starts, because the router keeps only the
   latest navigation. Unit tests and the Playwright journeys check both a protected page and a
   public one.
4. **Defaults to review (not agreed with the team).**
   - A signed-in user can no longer see the landing page at all; to read it they log out.
   - The logo means "my home" when signed in and "the front page" when not.

## Consequences
- Every role's home is pinned by a test that opens `/` signed in, with the paths written out.
- A new test proves logging out empties the query cache: a second coordinator on the same device
  no longer sees the first one's venue requests, which are cached by event rather than viewer.
  It needed a second Event Coordinator in the mock accounts (`idleCoordinator`, id 14).

## Revisit when
- The team wants signed-in users to reach the landing page (for example an "About" link).
- The logo should link straight to the role's home; that needs `homeFor` moved to `src/config`.
