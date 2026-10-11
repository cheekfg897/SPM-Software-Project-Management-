# frontend/CLAUDE.md

The ConnectSphere web app: React 19 + TypeScript, Vite, Tailwind CSS v4, Redux Toolkit (the
session only), TanStack Query (everything from the backend), React Router v8, MSW for mocks,
Vitest + Testing Library, and Playwright. The root `CLAUDE.md` still applies (readable over
clever, tests first, no decorative tests, helpers first, no repeated code, the definition of
done, Git rules). This file adds the frontend's rules.

## Commands

All from `frontend/` (`npm ci` first).

```bash
npm run dev               # app on :5173, /api proxied to BACKEND_URL (default http://localhost:5000)
npm run dev:mock          # app with every API call answered by src/mocks, no backend needed
npm run lint              # ESLint (type-aware); CI fails on any error
npm run format            # Prettier; CI runs `npm run format:check`
npm run typecheck         # tsc, strict
npm test                  # unit + component tests (Vitest, jsdom, MSW)
npm run test:coverage     # the same, with the coverage floor (90% on every measure)
npm run test:integration  # against a RUNNING backend: BACKEND_URL=http://localhost:5055 npm run test:integration
npm run test:e2e          # Playwright, desktop and mobile, against `dev:mock`
npm run build             # typecheck + production build
```

## The backend is the source of truth

The frontend shows what the backend says. It doesn't work things out for itself.

- **No client-side paging, filtering, sorting or counting.** A list screen sends its inputs
  (search text, date range, page) as query parameters and renders the page, the totals and the
  page count exactly as they come back.
- **Filter inputs live in the URL** (`useSearchParams`), not in component state or Redux. The
  URL is what gets sent, so a shared link shows the same results.
- **Errors are the backend's.** Show `error.message` (`<ErrorAlert>`) and the per-field messages
  (`fieldErrorsOf(error).<field>` into `<TextField errors>`). Don't write your own copy of a
  backend message, and don't re-implement backend validation (password rules, date rules,
  capacity limits). Plain HTML hints like `required` and `type="email"` are fine.
- **Don't branch on error codes** unless the screen really must behave differently (e.g. a 401
  sends the user to log in). Showing the message is enough for everything else.
- **API types use the backend's field names as they are** (`full_name`, `organisation_id`). No
  mapping layer renames them.
- **The only state the frontend owns is the session** (token and user) in Redux
  (`src/store`). Everything the backend knows is read through TanStack Query and never copied
  into Redux or `useState`.
- **After a change, invalidate the queries it affects** so they're read again. Don't patch the
  cache by hand to guess the new state.
- **A query key holds everything that changes the answer**, including who is asking when the
  response depends on the viewer (`is_registered`, `/me`). Otherwise signing in shows the
  previous viewer's copy.

## Layout

```
src/
  app/            App shell: providers, route table (routes.tsx), query client, NotFoundPage
  config/         constants used across features: ROUTES, ROLE and the role groups, BUSINESS_TIME_ZONE
  lib/api/        the ONLY place that calls fetch: apiRequest, ApiError, error helpers
  lib/            small shared helpers (isRecord, formatDate: Singapore dates and times)
  store/          Redux: the session slice, its persistence, typed hooks
  components/ui/  reusable primitives: Button, ButtonLink, TextField, ErrorAlert, Spinner, Badge, EmptyState
  components/layout/  SiteLayout, SiteHeader, SiteFooter, PageContainer, Logo
  features/<name>/
    api.ts        this feature's endpoint paths, response types, request functions, query keys
    hooks.ts      useQuery / useMutation wrappers around api.ts
    constants.ts  constants shared by several files in this feature (only if needed)
    components/   components only this feature uses
    pages/        the pages the route table points at
    test/         helpers only this feature's tests use (left out of coverage)
  mocks/          the mock backend (MSW):
    handlers/     one file per feature, plus index.ts (all handlers, resetMockBackend)
    fixtures/     data shared with e2e: accounts, tokens, sessions (relative imports, no msw)
    responses.ts  errorResponse, validationError, INVALID_TOKEN_MESSAGE in the backend's shape
    server.ts / browser.ts   the mock backend for Vitest / for dev:mock and e2e
  integration/    tests against the real backend (*.int.test.ts)
  test/           Vitest setup and shared helpers: renderWithProviders, renderApp, recordRequests
e2e/              Playwright journeys (*.spec.ts)
```

A feature never imports another feature's `components/` or `pages/`. If two features need the
same thing, move it to `components/`, `lib/` or `config/`.

## Talking to the backend

- **Everything goes through `apiRequest`** from `@/lib/api`. ESLint forbids `fetch` anywhere
  else. `apiRequest` adds the token, sends and reads JSON, and throws `ApiError` (the backend's
  `status`, `code`, `message` and `fieldErrors`) for any non-2xx or network failure. A 401 on a
  request that carried a token signs the user out.
- **Each feature's `api.ts` follows one pattern:**

  ```ts
  const CATALOGUE_PATHS = { EVENTS: '/api/events/catalogue' } as const

  export interface CatalogueEvent {
    id: number
    name: string
    starts_at: string
  }

  export const catalogueKeys = {
    all: ['catalogue'] as const,
    list: (params: CatalogueParams, viewerId: number | null) =>
      [...catalogueKeys.all, 'list', viewerId, params] as const,
  }

  export function fetchCatalogue(params: CatalogueParams): Promise<CataloguePage> {
    return apiRequest<CataloguePage>(CATALOGUE_PATHS.EVENTS, { query: { ...params } })
  }
  ```

- **`hooks.ts` wraps those functions** in `useQuery` / `useMutation`, and pages and components
  use the hooks. Components never call `apiRequest` or `api.ts` functions directly.
- **Mock handlers mirror the real responses**, including the error bodies. When the backend
  changes a shape, change the handler and the integration test together.
- **The mocks are one backend.** There is one set of users (`MOCK_ACCOUNTS` in
  `mocks/fixtures/accounts.ts`) and one token format (`mockTokenFor`, `mockSessionFor`). A
  handler that needs the caller uses the auth mock's `accountForRequest`, the way the backend's
  decorators do. A feature mock that keeps data (sign-ups, registrations) exports a
  `reset...()` and adds it to `resetMockBackend`, which runs after every test.

## Constants

- **Naming:** `SCREAMING_SNAKE_CASE` for module-level constant values (`MAX_RETRIES`,
  `SESSION_STORAGE_KEY`). A fixed set of named values is an `as const` object in the same case
  (`ROUTES`, `ROLE`), with a type derived from it:
  `type Role = (typeof ROLE)[keyof typeof ROLE]`. No TypeScript `enum` (`erasableSyntaxOnly`
  forbids them).
- **Where:** a constant used by one file sits at the top of that file. One used by several
  files in a feature goes in that feature's `constants.ts`. One used across features goes in
  `src/config/`.
- **No magic values in JSX or logic:** paths come from `ROUTES`, roles from `ROLE`, API paths
  from the feature's `*_PATHS`, colours from the theme tokens.
- **Plain constants for plain values:** `const X = 5`, not a function or a getter that returns 5.

## Types

- **No `any`.** `@typescript-eslint/no-explicit-any` is an error. Anything untrusted (decoded
  JSON, `localStorage`, `catch` variables) is `unknown`, narrowed with a type guard
  (`isRecord`, `isRole`) before use.
- **If `any` really can't be avoided** (e.g. a third-party type that forces it), disable the
  rule on that one line and say why after `--`. `eslint-comments/require-description` fails
  the lint without the reason:

  ```ts
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- <library> types its callback as any; narrowed on the next line
  ```

- **Type assertions (`as`) need a reason too.** The expected one is `apiRequest<T>`, which
  trusts the backend's shape (the integration tests check it). Anywhere else, prefer a type
  guard. If an assertion stays, add a comment saying why it's safe.
- `interface` for object shapes, `type` for unions and derived types. Export the types a
  caller needs, and nothing more.
- `strict`, `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes` are on. Handle the
  `undefined` rather than silencing it with `!`.

## Components

- **Reusable first.** Before writing a component, look in `components/ui` and
  `components/layout`. Extend one (a new `variant`, a new optional prop) rather than writing a
  near-copy. A second real use is when something moves into `components/`; the first stays in
  its feature.
- **One exported component per file**, named like the file. Small private pieces used only by
  that component may sit above it in the same file (helpers first).
- **As few props as possible.** No pass-through props a child could read itself (e.g. from the
  store), and no boolean props that switch between two different components. Two variants are
  two components, or a `variant` union.
- **Accessible by default:** every input has a `<label>`, errors are linked with
  `aria-describedby`, loading states say what's loading, icons carry `aria-hidden`, and
  interactive things are real `<button>` / `<a>` elements. Tests find elements by role and
  label, so an inaccessible component can't be tested.
- **Styling uses the theme tokens** in `src/index.css` (`bg-void`, `text-ink-muted`,
  `from-flare`). No raw hex values in components.
- **Motion respects `prefers-reduced-motion`:** scroll and ambient animation stop, and the
  page still makes sense without them.

## Tests

Tests come first. Write them from the story's ACs, watch them fail, then write the code. Each
test asserts something a user or the backend would notice, and goes red if that code broke.

| Layer                | What it proves                                                                                                                | Where                            | Tools                               | Runs against                 |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------- | -------------------------------- | ----------------------------------- | ---------------------------- |
| **Unit + component** | Helpers, hooks and components behave; screens show what the backend sent (data, empty, loading, error and field-error states) | next to the code: `*.test.ts(x)` | Vitest, Testing Library, user-event | MSW handlers (`src/mocks`)   |
| **Integration**      | The frontend's API functions and types match the **real** backend: request shapes, response shapes, error bodies, auth        | `src/integration/*.int.test.ts`  | Vitest, no mocks                    | a running backend + Postgres |
| **End-to-end**       | A user's whole journey in a real browser, desktop and mobile: navigate, fill in forms, see results                            | `e2e/*.spec.ts`                  | Playwright                          | the app in `dev:mock` mode   |

Rules:

- **Mock the network, never the code.** Component tests reach the backend through MSW. Don't
  `vi.mock` `apiRequest`, `fetch` or a feature's `api.ts`. Override one route in a test with
  `server.use(http.get(...))`. An unhandled request fails the test.
- **Render with the helpers:** `renderWithProviders(<Thing />, { session })` for one component,
  `renderApp(ROUTES.X, { session })` for a whole page with routing. Both return `user`
  (user-event), `store` and, for `renderApp`, `router`. Sign someone in with
  `session: mockSessionFor(MOCK_ACCOUNTS.attendee)`.
- **To check what was sent**, `const requests = recordRequests()` before acting, then read
  `requests` (clones, so bodies can be read). Recording stops after each test.
- **Assert on your own feature.** After a redirect, check the URL
  (`router.state.location.pathname`), not another feature's heading or copy, which can change
  under you.
- **Find elements the way a user does:** `getByRole`, `getByLabelText`, `getByText`. No test ids
  unless nothing else works.
- **Integration tests make their own data** (`uniqueEmail()`), never depend on another test's
  data, and only test endpoints that exist on the backend. An endpoint that is only a contract
  so far (e.g. the catalogue before SCRUM-52) gets `it.todo` there, and mocks elsewhere.
- **e2e tests cover journeys, not every edge case.** Edge cases belong in component tests.
- **Coverage:** `npm run test:coverage` enforces a 90% floor on lines, branches, functions and
  statements. Code you add or change should be fully covered. A line that can't be reached in
  jsdom gets `/* v8 ignore next -- <reason> */` (or `start` / `stop` around a block), and the
  reason is required (the same rule as the backend's `# pragma: no cover - <reason>`). Keep the
  ignored code thin: put the logic in a pure, tested module and leave only the drawing or
  wiring out (see `features/landing/blackHole/`). Browser-only wiring (`main.tsx`,
  `app/App.tsx`) and test helpers (`**/test/**`) are excluded; e2e covers the wiring.
- **Mark the story** in each test file's top `describe` or the file name when a file belongs
  to one story, e.g. `describe('SCRUM-52 catalogue', ...)`, so a story's tests are easy to find.

## Definition of done (frontend)

In order, and don't call it finished before the last one:

1. The tests were written first and seen failing.
2. `npm run lint`, `npm run format:check`, `npm run typecheck`, `npm run test:coverage` and
   `npm run build` pass. `npm run test:e2e` passes if a journey changed.
   `npm run test:integration` passes against a running backend if an API function changed.
3. Self-review against this file and `docs/code-review-checklist.md` (readability, reuse, no
   `any`, no client-side state that belongs to the backend). Fix what it finds and re-run step 2.
4. Report what the review found and fixed, anything left open, and any coverage exclusions.

## Git

Commit subjects follow the root `CLAUDE.md` (Conventional Commits naming the story, e.g.
`feat(SCRUM-65): sign up as an Event Organiser or Attendee`). Frontend-wide set-up and
conventions use SCRUM-5. Commits are layered, one logical change each, and each passes lint
and tests on its own.

## Gotchas

- **macOS port 5000 is AirPlay Receiver.** The dev proxy then gets a `403` that isn't from
  Flask. Run Flask on another port (`flask run --port 5055`) and start the frontend with
  `BACKEND_URL=http://localhost:5055 npm run dev`.
- **React Router v8:** import everything from `react-router`, except `RouterProvider` from
  `react-router/dom`. `react-router-dom` no longer exists (ESLint blocks it).
- **Mock mode is a Vite mode (`--mode mock`), not an env file.** The root `.gitignore` ignores
  every `.env.*`, so an env file wouldn't reach teammates or CI.
- **`public/mockServiceWorker.js` is generated by MSW** (`npx msw init public`). Commit it, and
  regenerate it after upgrading `msw`.
- **Date-times from the backend carry an offset** (`2026-10-01T17:00:00+08:00`, ADR-0009).
  Format them for display with `Intl.DateTimeFormat` in the `Asia/Singapore` time zone. Send
  date-times without an offset only where the backend documents that it reads them as business
  time.
- **Running e2e from two checkouts at once:** set `E2E_PORT` (e.g. `E2E_PORT=4181 npm run
test:e2e`). Locally Playwright reuses a server already on its port, which may be another
  checkout's code.
- **In mock mode the app mounts only after the mock worker starts.** An e2e test that lists
  elements (`locator.all()`) must first wait for one to be visible, or it checks an empty list
  and passes for nothing.
- **The header is `position: fixed`**, so something clipped inside it never widens the page. To
  test that it fits, measure the elements' boxes, not the page's `scrollWidth`.
- **Staff have no sign-up.** Their accounts come from `flask create-staff-user` (ADR-0023), so
  the staff login page never links to sign-up.
