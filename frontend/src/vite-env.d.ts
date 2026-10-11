/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "true" serves every API call from the mock handlers in src/mocks (no backend needed). */
  readonly VITE_API_MOCKING?: string
  /** The backend origin when it is not the page's own, e.g. http://localhost:5000 in integration tests. */
  readonly VITE_API_ORIGIN?: string
  /** Integration tests only: a staff account on the running backend, made with `flask create-staff-user`. */
  readonly INTEGRATION_STAFF_EMAIL?: string
  readonly INTEGRATION_STAFF_PASSWORD?: string
  /** A seeded Event Coordinator's sign-in for the integration tests that need one. */
  readonly VITE_COORDINATOR_EMAIL?: string
  readonly VITE_COORDINATOR_PASSWORD?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
