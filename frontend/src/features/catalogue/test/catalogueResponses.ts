import { http, HttpResponse } from 'msw'

import { server } from '@/mocks/server'

import type { CatalogueEvent, CataloguePage } from '../api'

/** Helpers for catalogue tests that need the backend to answer something exact. */

export const CATALOGUE_URL = '/api/events/catalogue'

let nextId = 1000

/** One event as the backend sends it; override only what the test cares about. */
export function catalogueEvent(overrides: Partial<CatalogueEvent> = {}): CatalogueEvent {
  nextId += 1
  return {
    id: nextId,
    reference: `EVR-TEST${nextId}`,
    name: `Event ${nextId}`,
    description: 'A test event.',
    starts_at: '2026-10-05T19:30:00+08:00',
    ends_at: '2026-10-05T22:00:00+08:00',
    venue: { id: 1, name: 'Esplanade Outdoor Theatre' },
    capacity: 100,
    places_left: 40,
    is_full: false,
    is_registered: false,
    ...overrides,
  }
}

export function cataloguePage(overrides: Partial<CataloguePage> = {}): CataloguePage {
  return { items: [], page: 1, page_size: 12, total: 0, total_pages: 0, ...overrides }
}

/** Answer every catalogue request with `page`. */
export function respondWithPage(page: CataloguePage): void {
  server.use(http.get(CATALOGUE_URL, () => HttpResponse.json(page)))
}

/** The query string of every catalogue request the page sends, in order. */
export function recordCatalogueQueries(): string[] {
  const queries: string[] = []
  server.events.on('request:start', ({ request }) => {
    const url = new URL(request.url)
    if (request.method === 'GET' && url.pathname === CATALOGUE_URL) {
      queries.push(url.searchParams.toString())
    }
  })
  return queries
}

// Importing this file stops recordCatalogueQueries' listeners after each test in that file.
afterEach(() => server.events.removeAllListeners())
