# Code review checklist

Use this for every PR you review, and on your own branch before you ask for review. Each item
links to the rule in [Python conventions](../backend/CONVENTIONS.md) (§ = section number);
frontend items follow [frontend/CLAUDE.md](../frontend/CLAUDE.md). Many items carry the real
case that taught it, so a reviewer can see why it is worth the time.

Items are ordered by cost of getting wrong: a missed module boundary or migration bug hurts the
whole team; a slightly vague name hurts one reader. If time is short, review from the top.

## 0. Before reviewing — let the machines go first

Don't review by hand what CI already checks. Confirm these are green (or run them locally from
`backend/`), then skip to section 1.

- [ ] **PR title** is `type(SCRUM-<id>): summary`; only `ci`/`build` may drop the
      `(SCRUM-<id>)` (`pr-title.yml`)
- [ ] **Lint**: `ruff check .` — style, imports, docstrings present, bandit security rules,
      no `date.today()` / naive `datetime.now()`
- [ ] **Format**: `ruff format --check .`
- [ ] **Tests + coverage**: `pytest -m "not e2e" --cov=app --cov-branch --cov-fail-under=100`
      passes (lines and branches, unit tests alone, ADR-0127), and so does `pytest -m e2e`
- [ ] **Changed lines covered**: the *Changed lines are fully covered* step (`diff-cover`)
      passes. It names lines only; a missed branch shows in the `Missing` column.
- [ ] **Migrations**: one Alembic head; `flask db check` clean; downgrade → upgrade replays
- [ ] **App boots**: `/health` smoke test passes
- [ ] **Frontend** (from `frontend/`): `npm run lint`, `npm run format:check`, `npm run typecheck`,
      `npm run test:coverage` and `npm run build`; `npm run test:e2e` if a journey changed;
      `npm run test:integration` against a running backend if an API function changed. On
      Windows, `format:check` lists nearly every file because of CRLF line endings; check the
      changed files with `npx prettier --check <files>` (CI runs on Linux and is unaffected).
- [ ] **Secret scanning** (GitGuardian) is green. See section 5 before dismissing a finding.
- [ ] **Every required check reported.** A required check stuck at "Expected — Waiting for
      status to be reported" never started for the latest commit; close and reopen the PR to
      run it, rather than waiting.

Mypy isn't in CI yet, so type hints are reviewed by hand in section 8.

## 1. Scope and traceability

- [ ] The PR does one story (or one clearly-scoped fix). Unrelated changes are split out.
- [ ] **Commits are layered** (§15): one logical change each, each passing lint and tests
      on its own, in dependency order, with no "WIP" or "fix previous commit" commits.
- [ ] Every acceptance criterion of the story is implemented and tested — check against the
      **Jira story** (the single source of truth for requirements), one AC at a
      time. Read its comments too: agreed clarifications live there.
- [ ] **Re-read the Jira story, and its `updated` date, right before the verdict**, not only at
      the start, and look for follow-up branches on the same story (`git branch -r | grep
      SCRUM-<id>`). Week 7 rewrote SCRUM-24 AC2 the night before #35 merged.
- [ ] **Build the case list from each AC first**: valid, invalid, boundary, each role allowed
      and refused, and rows that existed before the change. Map each case to a test; the
      cases left over are the missing tests.
- [ ] Anything an AC mentions that doesn't exist yet ("bookings", "registrations") is in an
      ADR's **Deferred** or **Blocked** section, naming the story that delivers it.
- [ ] **If Jira changed after the code was written**, the AC numbers cited in code and tests
      match the *current* list, and new ACs are recorded as Blocked or Deferred in the ADR with
      the reason. Check the reason, not just the label.
- [ ] **A story whose ACs need a screen stays not Done** when its backend merges; the approval
      says what makes it Done (see *Leaving review comments*).
- [ ] Open "Ask customer" subtasks on the story that this change depends on have an ADR
      recording the interim decision.
- [ ] Nothing beyond the story was added (no speculative options, abstractions or endpoints).
- [ ] Where the ACs were ambiguous, the decision is recorded as an ADR in `docs/adr/` and the
      index table is updated.
- [ ] The PR description's **Decisions made** lists each of those decisions with its ADR, split
      into agreed and defaults to review. **Tickets to open** lists the follow-ups found,
      including new `# TODO`s. Both say "None" if empty (§15).
- [ ] New test modules set `pytestmark` to the story's marker, and the marker is declared in
      `pytest.ini`.
- [ ] `README.md` route table and `.env.example` are updated if the change affects them.

## 2. Architecture and module boundaries (§7)

- [ ] No module imports another module's `models`. Cross-module access goes through that
      module's `services.py` (or `auth.permissions` for roles).
- [ ] Cross-module foreign keys are DB-level `ForeignKey(...)` only — no `relationship()` to
      another module's model.
- [ ] Nothing in `app/common/` imports from `app/modules/`.
- [ ] Routes are thin: parse → call a service → serialise. No validation, queries or business
      rules in `routes.py`.
- [ ] Services don't touch `request` or `g`; the route passes in what they need.
- [ ] A new module has `register(app)` and is added to `_register_modules` in
      `app/__init__.py`.
- [ ] No reimplementation of something that already exists (`load_or_raise`, `local_today`,
      `resolve_session`, `invalid_token_response`, `role_value`,
      `error_response`, `normalise_email`, the role groups...).
- [ ] Service functions take `session` (and `today` / factories where relevant) as keyword-only
      arguments with production defaults.

## 3. Correctness

- [ ] Trace each AC through the code by hand with one valid input and one invalid input.
- [ ] Boundaries are right: `<` vs `<=`, today vs yesterday, 0 vs 1, empty string vs
      whitespace vs `None`, first vs last retry attempt.
- [ ] `None`/missing values are handled wherever the type says `| None`.
- [ ] Type coercions are explicit and safe (e.g. token identity `str` → `int(...)`).
- [ ] Every `commit()` that can fail is followed by `rollback()` on the failure path.
- [ ] Retries have a bound, and only retry errors that a retry can fix.
- [ ] Race conditions: a "check then insert" is backed by a DB constraint, and the
      `IntegrityError` is translated into the right `AppError`.
- [ ] List endpoints have a deterministic order (tie-breaker on `id`).
- [ ] **Rows that existed before this change still work**: a new rule doesn't crash on data the
      old rules allowed (e.g. organisers who signed up before organisations existed get a
      clear `403`, not a `500`).
- [ ] **Which fields come from the server, never the client?** The actor, the owner's
      organisation, ids and status are set from the token or the database, never the body.

## 4. Readability — the one-read test (guiding principle)

Readable beats clever. Correct code that a teammate can't follow in one read is a **should**
finding, not a nit.

- [ ] Could a teammate who didn't write this understand each function in one read, without
      asking the author?
- [ ] The obvious version is used: plain loops and `if`s over dense comprehensions, nested
      conditional expressions or chained one-liners.
- [ ] Intermediate results have names; early returns instead of deep nesting.
- [ ] No tricks: metaprogramming, dynamic `getattr` dispatch, custom descriptors, operator
      overloading, or truthiness checks where `is None` / `== 0` is meant.
- [ ] Follows the patterns already in the codebase instead of inventing a new one.
- [ ] **Judge against the codebase's pattern, not an ideal.** If the change does what its
      neighbours already do, that isn't this PR's finding; a module-wide weakness gets its own
      ticket.
- [ ] Check `app/common/` (and the frontend's `components/ui`, `lib`, `config`) before writing a
      helper. A copy with a justification in its docstring still reads as drift.
- [ ] Shared helpers take only the arguments they need: no pass-through keyword arguments, and
      module-specific logic stays in that module.
- [ ] Functions do one thing; a long function is split where that makes it clearer (not into
      one-line helpers that force the reader to jump around).
- [ ] **Helpers first** (§2): every helper sits above the functions that use it, so the file
      reads top to bottom.
- [ ] **No repeated code** (§7): no block, condition or query appears twice — in tests either
      (use `parametrize` and fixtures). No helper created for a single "future" use.
- [ ] **As few arguments as possible** (§7): no unused or pass-through parameters, no
      boolean flags that switch behaviour, and no hidden inputs read from `g`/`request`/globals
      to avoid an argument. Test seams (`session`, `today`, factories) are exempt.
- [ ] No comment is needed to explain *what* a line does — if one is, the code is rewritten.

## 5. Security (§12)

- [ ] Every non-public route has `@requires_auth` or `@requires_role(...)`, and the allowed roles
      match the story — not wider.
- [ ] Roles come from `Role` / role groups, never string literals.
- [ ] The acting user comes from `g.current_user_id`, never from the request body or URL.
- [ ] Reads are scoped to what the caller may see (e.g. an organiser's, filtered by their
      client organisation).
- [ ] Input schemas don't declare server-controlled fields (`id`, `status`, `reference`,
      owner ids).
- [ ] Output schemas don't expose internal ids, password hashes or other users' data.
- [ ] Error messages don't reveal internals or enable enumeration (login failures are generic).
- [ ] No secrets, real credentials or `.env` files committed. New config comes from env vars and
      is added to `.env.example`.
- [ ] **No password-like name next to a value**, test data included (`password: '…'`,
      `WEAK_PASSWORD = '…'`): secret scanning flags it. Reuse an existing fixture or account
      instead. GitGuardian scans **every commit** in the PR, so a later commit removing the line
      doesn't clear it; the line has to leave the commit that added it.
- [ ] Workflows name secrets (`${{ secrets.NAME }}`), never their values, and pass them through
      `env:` rather than into the `run:` line. A value made up during a CI run is masked
      (`::add-mask::`). A real token that was ever committed is revoked: closing the PR or
      deleting the branch doesn't remove it.
- [ ] Scope is judged against the story's "so that…": SCRUM-7 says organisers must never see
      another client's confidential events, so a cross-organisation leak is a **must** even if
      the events look harmless.
- [ ] Security-relevant randomness uses `secrets`, not `random`.
- [ ] No SQL built with string formatting.
- [ ] Every `# noqa: S...` has a written justification that holds up.
- [ ] Nothing sensitive is logged (passwords, tokens, full request bodies).

## 6. Errors and validation (§8, §9)

- [ ] Failures raise an `AppError` subclass with the right status; routes never build error
      responses by hand.
- [ ] Exceptions are chained with `from exc` and caught as narrowly as possible.
- [ ] Every request body goes through a schema via `load_or_raise`.
- [ ] Cross-field rules use `@validates_schema` with `field_name=` so the error points at the
      right field.
- [ ] User-facing messages are clear, specific and consistent in tone with existing ones.
- [ ] Strict types: integers reject booleans, booleans accept only `true`/`false`, times reject
      offsets where relevant.
- [ ] Each field's **format** is checked, not just its length. Ask what it is for:
      `contact_phone` accepted `"abc"` because it only had a maximum length.
- [ ] "Required" also means **not blank**: `Length(min=1)` accepts `"   "`. Use `not_blank` and
      trim in `post_load`, on create and on update.
- [ ] Cross-field rules still hold under **PATCH**: a `@validates_schema` comparing two fields is
      skipped when only one is sent, so re-validate against the merged values.
- [ ] Values joined with a separator reject items that contain it, or they come back split.
- [ ] An edit that sends unchanged values back (an edit form re-sending the same name) isn't a
      conflict, and an empty update keeps the record.

## 7. Database and migrations (§10)

- [ ] Every model change has a migration in this PR, and the migration was read, not just
      generated.
- [ ] File named `NNNN_<verb>_<thing>.py`, readable `revision` id, `down_revision` points at
      the current head on `main`, module docstring names the story.
- [ ] `downgrade()` fully reverses `upgrade()`, including dropping Postgres enum types.
- [ ] No merged migration was edited.
- [ ] Constraints and indexes follow the naming convention (`uq_`, `ck_`, `ix_`), and names
      that code refers to live in a module constant.
- [ ] Invariants are enforced in the DB as well as the schema (`nullable=False`, unique, check).
- [ ] Timestamp columns are `DateTime(timezone=True)`; enum columns store values via
      `values_callable`.
- [ ] Columns that get filtered on have an index.
- [ ] No N+1 query patterns (a query inside a loop over query results).
- [ ] Every user-supplied value is **capped to its column, numbers too**: SQLite ignores
      `String(n)` and integer range, so CI passes while Postgres answers with a `500`. For a
      joined list, derive the item count and length from the column width.
- [ ] A new nullable column has a backfill (or a `NOT NULL DEFAULT`), and the code handles
      `None` for older rows.

## 8. Types (§4)

- [ ] Every function, including tests and private helpers, has full parameter and return
      annotations.
- [ ] Modern syntax: `list[...]`, `X | None`, `collections.abc` types.
- [ ] `Any` only at genuinely dynamic boundaries.
- [ ] Nullable columns are `Mapped[T | None]`, and the annotation matches `nullable=`.
- [ ] Every `# type: ignore` has a specific error code and is actually needed.

## 9. Dates and time (§11)

- [ ] Business dates come from `local_today()`; instants use `datetime.now(timezone.utc)`.
- [ ] Logic that depends on "today" takes it as a parameter, and tests pin it.
- [ ] Date/time comparisons don't mix naive and aware values.
- [ ] Dates are shown in business time whatever the device's time zone (ADR-0009), and date
      display is tested in a zone where a wrong conversion shows. Singapore and CI's UTC both
      hide a date shifted by a day; a zone behind UTC (e.g. `America/Los_Angeles`) doesn't.

## 10. Tests (§14)

- [ ] Tests were written first, from the ACs. For a self-review: were they seen failing before
      the implementation existed?
- [ ] Every AC has at least one test, and the module docstring says which ACs/ADRs it covers.
- [ ] Rejection paths and boundaries are tested, not just the happy path.
- [ ] **AC table first.** Before judging tests, list for each AC one row per test with what it
      sets up and what it expects (read the body, not the name), and what *isn't* tested.
      The gaps show up in the table, not in a skim.
- [ ] **No decorative tests:** each test asserts an observable outcome (value, error + status,
      saved fields, log line), states the expected value literally, and would fail if the key
      line were deleted or its condition inverted. Try it on the most important ones.
- [ ] **Mutation-test the key lines yourself**: break one line (invert a condition, widen a
      filter, drop a role, swap a field), run the tests, expect red, restore. Then the cases
      nobody wrote code for: drop one member from each allow-list, add one to each deny-list,
      send wrong types. A script that edits code must refuse a target it finds 0 or 2+ times.
      100% coverage only shows a line *ran*: the equipment catalogue had full coverage and 7 of
      48 breakages still passed. A surviving mutant is a gap unless no input could tell the two
      versions apart (an *equivalent mutant*).
- [ ] **Every allowed value appears in a test, as a match**: each allowed character, enum
      member and role. Changing a phone pattern's `[0-9]` to `[0-8]` passed every test,
      because no test number contained a 9; of six venue layouts only one was ever tested as a
      match. Build lists of refused values from the enum minus the allowed values written out,
      so a value added later is tested automatically.
- [ ] **Deny-lists are tested on the side they let through**, for every member, including states
      the normal flow can't reach (write them straight into the table). Adding `draft` to the
      "equipment not needed" list passed all 27 tests until one showed a draft being listed.
- [ ] **Boundaries on both sides**: the exact edge and one step past it (`17:00:00` and
      `16:59:59` for `>=`; 7 and 8 digits).
- [ ] **Values a bug can't produce by accident**: log in as an id no fixture or default uses (42
      or 999, not 1 or 7), test two inputs where the answers should differ, and create two of
      something whose id could coincide (in a fresh database the first user and the first
      organisation are both id 1).
- [ ] **Decoys sit where the bug would bite.** A filter is tested with the wrong data placed
      where it could be mistaken: an unrelated history entry *between* a question and its
      answer, not before it, where it was skipped anyway.
- [ ] **Wrong types for every field**: numbers as `"1"`, `1.5`, `true` and null (`venue_id`
      accepted `true` as venue 1); text as a number; the body as nothing, a list or a string.
- [ ] **Assert why it was refused**, not just the status: the field and its message, so a test
      can't pass for the wrong reason ("Venue not found" instead of "Not a valid integer.").
- [ ] **Route wiring**: assert the exact id and body the route passes to its service and the JSON
      it returns, with an id no default produces.
- [ ] **Write-route permissions**: every other role gets `403`, no token gets `401`, the service
      isn't called, and the view's `allowed_roles` is pinned.
- [ ] SQL filters and ordering are tested on `db_session`, not `mock_session`: a mock ignores
      the query, so `>=` can become `<=` with every test still green.
- [ ] Config-driven defaults are tested with an unusual value, not by comparing the config key
      with itself.
- [ ] When an AC fixes the wording of a message, the test asserts that exact text.
- [ ] **Full coverage:** CI's floor holds every line and branch, on unit tests alone. Each
      new `# pragma: no cover - <reason>` gives a reason that really holds.
- [ ] Test names describe the behaviour in a sentence.
- [ ] Deterministic: no real clock, no real randomness, no sleeps, no dependence on test order.
- [ ] Side effects that matter are asserted (`add`, `commit`, `rollback` calls).
- [ ] Shared setup uses existing fixtures/factories, or adds a new one to `conftest.py`.
- [ ] Any new `# pragma: no cover` has a reason and really can't be unit-tested; every gap
      is listed with its reason in the PR description.
- [ ] **The frontend's contract:** if the change alters a response, error body or validation
      rule the frontend uses, or ships an endpoint a frontend `it.todo` is waiting for, the
      integration tests in `frontend/src/integration/` and the mock handlers in
      `frontend/src/mocks/handlers/` are updated in the same PR, or listed under **Tickets to
      open**.

## 11. Naming, docs and style (§3, §5)

- [ ] Names follow the conventions table and use British spelling (`organiser`, `normalise`).
- [ ] Names say what a thing is in domain terms; no unexplained abbreviations.
- [ ] Docstrings follow Google style, give HTTP status in `Raises:`, and reference the story/ADR
      behind a rule.
- [ ] Comments explain *why*, not *what*. No stale or commented-out code.
- [ ] `TODO`s are real follow-ups (`# TODO:` / `# TODO(product):`), not unfinished work in this
      story.
- [ ] Logs use `connectsphere.<module>` loggers and `event_name key=value` with lazy `%`
      args.
- [ ] **Stale text** is updated: docstrings, the README route table, AC numbers in code and tests
      against Jira's *current* list, and ADR statuses. When an ADR is superseded, the old ADR's
      own Status line says so, not just the index.
- [ ] A leading `_` means private to the file; anything another module imports is public. Nothing
      is named after a format it doesn't really implement (`_to_csv` did no CSV quoting).

## 12. Frontend ([frontend/CLAUDE.md](../frontend/CLAUDE.md))

- [ ] **The backend is the source of truth**: no paging, filtering, sorting or counting in the
      browser; filter inputs live in the URL; lists keep the order the backend sent.
- [ ] **The backend's words are shown, not rewritten**: `error.message` and per-field errors,
      and messages like an empty list's (test it with a message only the backend could have
      sent). No re-implemented backend validation, and no branching on error codes unless the
      screen must behave differently.
- [ ] API types use the backend's field names as they are. Only the session lives in Redux;
      everything else is read through TanStack Query, invalidated after a change, with a query
      key that includes the viewer when the answer depends on who asks.
- [ ] **Feature boundaries**: no feature imports another's `components/` or `pages/`; the route
      table in `app/` puts features together. Something a second feature needs moves to
      `components/ui`, `lib` or `config` in its own commit, and a constant used across features
      lives in `src/config/`.
- [ ] Every call goes through `apiRequest`; components use `hooks.ts`, never `api.ts` directly.
- [ ] **Mock handlers mirror the real backend**, error bodies and exact messages included, and
      decide scope and order the way it does; their test data contains the rows a leak would
      show first.
- [ ] **Tests mock the network, never the code** (MSW, `server.use` for one route), and find
      elements by role and label, like a user.
- [ ] No `any`, no `enum`, and every `as` has a reason; theme tokens, not hex values; inputs have
      labels and decorative icons are `aria-hidden`.
- [ ] **Looks like the rest of the app**: built from the nearest existing component (e.g. the
      catalogue's `EventCard` for anything listing events), with its tokens, type scale and
      voice, not a fresh generic design.
- [ ] e2e steps wait for what a user would see before the next step (the URL holding the first
      filter, the first row being visible), or they race or pass on an empty page.

## 13. Git, branches and PRs (§15)

- [ ] **No leftover conflict markers**: `git diff --check` is clean before a resolved conflict is
      committed.
- [ ] **A reviewer's fixes are their own commits** on top of the author's, named as standalone
      changes (`test(SCRUM-xx): check …`), so each person is credited for their work. Fold into
      the author's commit (`--fixup` + autosquash) only when a line must leave that commit,
      e.g. a secret.
- [ ] **Stacked PRs**: after the PR below merges with Rebase and merge, its commits have new ids;
      update with **▾ → Update with rebase**, not the plain button, or rebuild with
      `git switch --no-track -C <branch> origin/main` and `git cherry-pick <old base>..<old head>`,
      count the commits, and push the rebuild straight away with `--force-with-lease`.
- [ ] **Delete a merged branch at once**, and change any PR still targeting it to `main` first:
      deleting a branch an open PR targets closes that PR, and a leftover branch can become the
      next PR's base.
- [ ] The PR description's test count and stack notes are updated after every rebuild.

## Leaving review comments

- Prefix comments so the author knows what's blocking:
  - **must:** — has to change before merge (bug, security, boundary, missing test for an AC).
  - **should:** — worth changing; author can push back with a reason.
  - **nit:** — minor preference; never blocks.
  - **question:** — you want to understand, not necessarily change.
- Point to the rule (`§7 module boundaries`) or a concrete failure case, rather than "I'd do
  it differently". For a test gap, give the mutation that survived and the test that would
  catch it.
- Judge severity against the story's "so that…" and its ACs, not personal preference.
- Comment inline only on findings and changes. Put the verification of a clean PR in the
  approval message: what was checked (ACs, mutations and which test caught each) and any
  commits you added, so the depth of the review is visible.
- **When a story stays not Done after merging**, the approval lists what makes it Done, one item
  each: the AC, what's missing, who or what delivers it (a story, the frontend, the customer),
  and an observable "done when".
- Code that merged without a review still gets one afterwards; a gap found then becomes a
  small follow-up PR with the surviving mutation in its commit message.
- When a teammate's test catches something this checklist doesn't cover, add it here.
- If a convention here turns out to be wrong, fix the doc in its own PR rather than arguing it
  in every review.
