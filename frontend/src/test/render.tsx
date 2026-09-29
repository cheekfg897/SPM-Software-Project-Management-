import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement, ReactNode } from 'react'
import { Provider } from 'react-redux'
import { createMemoryRouter, MemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'

import { appRoutes } from '@/app/routes'
import { createAppStore, signedIn } from '@/store'
import type { SignedInPayload } from '@/store'

interface RenderOptions {
  /** Sign this user in before rendering. Leave out to render signed out. */
  session?: SignedInPayload
}

/** A query client for one test: no retries, so an error shows up at once. */
function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function createTestStore(session: SignedInPayload | undefined) {
  const store = createAppStore()
  if (session) {
    store.dispatch(signedIn(session))
  }
  return store
}

function Providers({
  store,
  children,
}: {
  store: ReturnType<typeof createAppStore>
  children: ReactNode
}) {
  return (
    <Provider store={store}>
      <QueryClientProvider client={createTestQueryClient()}>{children}</QueryClientProvider>
    </Provider>
  )
}

/** Render one component with the store, the query client and a router around it. */
export function renderWithProviders(ui: ReactElement, { session }: RenderOptions = {}) {
  const store = createTestStore(session)
  const result = render(
    <Providers store={store}>
      <MemoryRouter>{ui}</MemoryRouter>
    </Providers>,
  )
  return { ...result, store, user: userEvent.setup() }
}

/** Render the whole app at `path`, as a visitor landing on that URL would see it. */
export function renderApp(path: string, { session }: RenderOptions = {}) {
  const store = createTestStore(session)
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
  const result = render(
    <Providers store={store}>
      <RouterProvider router={router} />
    </Providers>,
  )
  return { ...result, store, router, user: userEvent.setup() }
}
