/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "true" serves every API call from the mock handlers in src/mocks (no backend needed). */
  readonly VITE_API_MOCKING?: string
  /** The backend origin when it is not the page's own, e.g. http://localhost:5000 in integration tests. */
  readonly VITE_API_ORIGIN?: string
  /** Integration tests only: a staff account on the running backend, made with `flask create-staff-user`. */
  readonly INTEGRATION_STAFF_EMAIL?: string
  readonly INTEGRATION_STAFF_PASSWORD?: string
  /** Optional: a Venue Staff account, for the booking decision checks (SCRUM-43). They skip without it. */
  readonly INTEGRATION_VENUE_STAFF_EMAIL?: string
  readonly INTEGRATION_VENUE_STAFF_PASSWORD?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
