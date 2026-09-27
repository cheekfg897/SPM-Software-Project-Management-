# ADR-0031: The request-to-approval journey is one end-to-end test, driven through Flask's test client

- **Status:** Accepted
- **Date:** 2026-09-27
- **Story:** SCRUM-41 End-to-end test: request to approval
- **Makes an exception to:** the unit-only testing rule (CLAUDE.md "Gotchas", CONVENTIONS §14 "Style"): no Flask test client and no real DB

## Context
SCRUM-41 has three ACs. One automated test covers draft, submission, coordinator assignment, clarification, resubmission and approval as a single journey (AC1). It runs in the pipeline, and a failure blocks the merge (AC2). A comment names the user stories and ACs it exercises (AC3).

Every step already has unit tests: the services run against `mock_session` or the in-memory `db_session`, and the routes run as view functions inside `app.test_request_context(...)`. What no test shows is that the steps fit together: that the status one step leaves is the one the next step accepts, and that each user sees what the others did.

That leaves these questions open:
1. Which layer the journey drives, since the suite is unit tests only.
2. Where it lives, and how it is marked.
3. What the shared harness holds, and where.
4. The test's shape: one test, or one per step.
5. How the users come to exist.
6. How the proposed date avoids depending on the day the test runs.
7. What is checked along the way.
8. Whether the rejection path gets its own journey.
9. What "red" means for a test that passes on arrival.
10. How AC2 is met.

## Decision
1. **The HTTP layer, through `app.test_client()`, on the in-memory database (41-1, agreed with the user).** Real URL routing, `@requires_role`, JSON parsing, `load_or_raise`, the `AppError` handlers and the output schemas all run. Flask reuses the application context the autouse `app_context` fixture pushed, and Flask-SQLAlchemy scopes `db.session` by application context, so a route's `db.session` is the test's `db_session`. The alternatives:
   - (b) chaining the service functions would re-run existing unit tests in sequence, and never exercise the routes, the tokens or the 409s a client sees;
   - (c) running against CI's Postgres is deferred (see "Revisit when").
2. **`tests/e2e/`, marked `scrum_41` and `e2e` (41-2).** The `e2e` marker makes the exception checkable: `pytest -m "not e2e"` is exactly the unit suite.
3. **The harness is mechanism only (41-3, 41-16).** `tests/e2e/conftest.py` holds the `client` fixture and the `sign_in` fixture, which logs in over `POST /api/auth/login` and returns an `Actor`. `Actor` is a frozen dataclass whose `get`, `post` and `patch` calls carry the Bearer token. It lives in the plain module `tests/e2e/actors.py`, because a conftest holds only fixtures. Accounts and journey constants stay in the test module. Three smoke tests in `test_harness.py` prove the harness before the journey relies on it (41-18):
   - the token identifies its user;
   - a request without the token gets `401`;
   - data flows both ways between a route and `db_session`.
4. **One test, with a banner comment per step naming its ACs (41-4).** A chain of per-step tests would depend on test order.
5. **The coordinator is created as staff are (41-5).** That means `create_staff_user` (ADR-0023), on `db_session`. Everything else goes over HTTP: the coordinator records the client organisation, and the organiser registers with it and logs in.
6. **The proposed date is `local_today() + 30 days`, and no times are asserted (41-6).**
7. **Every step is checked where the users would see it (41-7, 41-12).** Assignment is checked on both users' records, on the coordinator's assigned list and on both users' latest notices. At the end, the organiser's record shows the decision and the clarification exchange, and the history kinds are checked in order.
8. **No rejection journey (41-8).** AC1 names approval, and the unit tests cover rejection.
9. **Mutation checks are the red step (41-9).** The orchestrator applied each mutation independently in a scratch copy, and each one turned the journey red at its own step:
   - removing the `under_review` status change in `resubmit_event_request` fails step 6;
   - skipping `_check_no_clarification_outstanding` fails step 5 (`200`, not `409`);
   - dropping `_notify_organiser_of_decision` fails step 7;
   - dropping the organiser's `request_assigned` notice fails step 3;
   - removing the status change in `start_event_request_review` fails step 4.
10. **AC2 is met by the existing backend CI job (41-10).** It runs the whole suite, `tests/e2e` included. No separate job is added.

The remaining choices:
- The organiser amends the attendance from 250 to 300 when answering, so a `field_changed` entry appears in the history (41-11).
- An explicit `/review` step comes before the clarification (41-13).
- The work lands as separate commits: the markers, the harness, the journey, then these docs (41-14).
- The docs are updated as follows (41-15): this ADR, CLAUDE.md's gotcha, CONVENTIONS §14, README §5, and the docstrings that promised HTTP tests "next sprint".

## Consequences
- The test client appears in exactly one conftest. Everywhere else, the unit-only rule stands.
- A change that breaks how the stories fit together now fails the suite even when every unit test passes. Changing a route's path, status code, response shape or notification kind means updating the journey too.
- The journey adds about a second to the suite. The JWT's 60-second test expiry is far longer than the journey takes.
- SQLite enforces neither enums nor foreign keys, so those remain CI's migration steps' job.

## Open items
- **41-10:** the repo owner must confirm that the backend check ("Backend — migrate + unit tests") is a **required** status check on `main`. Until then, a red journey is reported on the PR but doesn't block the merge, and AC2's "blocks the merge" is not met.

## Revisit when
- CI sets a `TEST_DATABASE_URL` for Postgres. Running the journey against the migrated schema (option c) would also check enums and foreign keys, but `db_session`'s `create_all`/`drop_all` would first have to give way to the migrations.
- A second journey is added, for example rejection or venue booking. Its helpers (`_body`, `_latest_notification`, `_record`) might then move into `tests/e2e/`, beside `actors.py`.
- The frontend is chosen. A browser-level test might replace or sit above this one.
