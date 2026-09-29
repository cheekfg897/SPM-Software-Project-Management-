import { apiRequest, connectApiClient } from '@/lib/api'
import { server } from '@/mocks/server'

import { createCatalogueHandlers } from './catalogue'
import { MOCK_CATALOGUE_TOKENS } from './catalogueFixtures'

/**
 * The catalogue mock is the stand-in for SCRUM-52's backend, so these tests pin it to the
 * contract in docs/adr/0032-event-catalogue-contract.md. The fixture's "now" is Monday
 * 2026-10-05 12:00 in Singapore.
 */

interface Page {
  items: {
    id: number
    name: string
    starts_at: string
    is_registered: boolean
    places_left: number
    is_full: boolean
  }[]
  page: number
  page_size: number
  total: number
  total_pages: number
}

const CATALOGUE = '/api/events/catalogue'

function signInAs(token: string | null) {
  connectApiClient({ readAccessToken: () => token, handleUnauthorised: () => undefined })
}

function fetchPage(query: Record<string, string> = {}) {
  return apiRequest<Page>(CATALOGUE, { query })
}

function register(eventId: number) {
  return apiRequest(`${CATALOGUE}/${eventId}/registrations`, { method: 'POST' })
}

function startDates(page: Page): string[] {
  return page.items.map((item) => item.starts_at.slice(0, 10))
}

beforeEach(() => {
  server.use(...createCatalogueHandlers())
  signInAs(null)
})

afterAll(() => signInAs(null))

describe('SCRUM-52 catalogue mock: listing', () => {
  it('lists upcoming events soonest first, 12 to a page, with totals', async () => {
    const page = await fetchPage()

    expect(page.page).toBe(1)
    expect(page.page_size).toBe(12)
    expect(page.items).toHaveLength(12)
    expect(page.total_pages).toBe(Math.ceil(page.total / 12))
    const starts = page.items.map((item) => item.starts_at)
    expect([...starts].sort()).toEqual(starts)
  })

  it('leaves out an event that has already ended today', async () => {
    const page = await fetchPage({ when: 'today' })

    expect(page.items.map((item) => item.name)).not.toContain('Sunrise Yoga on the Lawn')
    expect(startDates(page).every((date) => date === '2026-10-05')).toBe(true)
    expect(page.total).toBeGreaterThan(0)
  })

  it.each([
    ['this_week', '2026-10-05', '2026-10-11'],
    ['this_weekend', '2026-10-10', '2026-10-11'],
  ])('resolves %s in business time', async (when, first, last) => {
    const page = await fetchPage({ when, page_size: '50' })

    expect(page.total).toBeGreaterThan(0)
    expect(startDates(page).every((date) => date >= first && date <= last)).toBe(true)
  })

  it('filters by a custom range read as business time', async () => {
    const page = await fetchPage({ starts_from: '2026-10-20T00:00', starts_to: '2026-10-25T23:59' })

    expect(page.total).toBeGreaterThan(0)
    expect(startDates(page).every((date) => date >= '2026-10-20' && date <= '2026-10-25')).toBe(
      true,
    )
  })

  it('searches name, description and venue without regard to case', async () => {
    const byName = await fetchPage({ q: 'JAZZ' })
    const byVenue = await fetchPage({ q: 'esplanade' })

    expect(byName.items.map((item) => item.name)).toContain('Jazz by the Bay')
    expect(byVenue.total).toBeGreaterThan(0)
  })

  it('returns an empty page past the last one, with the real totals', async () => {
    const page = await fetchPage({ page: '99' })

    expect(page.items).toEqual([])
    expect(page.total).toBeGreaterThan(0)
    expect(page.page).toBe(99)
  })

  it.each([
    [{ when: 'someday' }, 'when'],
    [{ when: 'today', starts_from: '2026-10-20T00:00' }, 'when'],
    [{ starts_from: '2026-10-25T00:00', starts_to: '2026-10-20T00:00' }, 'starts_to'],
    [{ starts_from: 'not a date' }, 'starts_from'],
    [{ page: '0' }, 'page'],
    [{ page_size: '51' }, 'page_size'],
  ])('refuses %j with a message on %s', async (query, field) => {
    const error = await fetchPage(query).catch((caught: unknown) => caught)

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error).toHaveProperty(['fieldErrors', field])
  })
})

describe('SCRUM-52 catalogue mock: registering', () => {
  async function firstOpenEventId(): Promise<number> {
    const page = await fetchPage()
    const open = page.items.find((item) => !item.is_full && !item.is_registered)
    if (open === undefined) {
      throw new Error('The fixture has no open event on page 1.')
    }
    return open.id
  }

  it('registers an attendee, who then shows as registered with one place fewer', async () => {
    signInAs(MOCK_CATALOGUE_TOKENS.ATTENDEE)
    const eventId = await firstOpenEventId()
    const before = (await fetchPage()).items.find((item) => item.id === eventId)

    await expect(register(eventId)).resolves.toMatchObject({
      event_id: eventId,
      status: 'registered',
    })

    const after = (await fetchPage()).items.find((item) => item.id === eventId)
    expect(after?.is_registered).toBe(true)
    expect(after?.places_left).toBe((before?.places_left ?? 0) - 1)
  })

  it('refuses a second registration for the same event', async () => {
    signInAs(MOCK_CATALOGUE_TOKENS.ATTENDEE)
    const eventId = await firstOpenEventId()
    await register(eventId)

    await expect(register(eventId)).rejects.toMatchObject({
      status: 409,
      code: 'already_registered',
    })
  })

  it('refuses a full event', async () => {
    signInAs(MOCK_CATALOGUE_TOKENS.ATTENDEE)
    const full = (await fetchPage({ page_size: '50' })).items.find((item) => item.is_full)

    await expect(register(full?.id ?? 0)).rejects.toMatchObject({ status: 409, code: 'event_full' })
  })

  it('refuses anyone who is not an attendee', async () => {
    signInAs(MOCK_CATALOGUE_TOKENS.ORGANISER)

    await expect(register(await firstOpenEventId())).rejects.toMatchObject({
      status: 403,
      code: 'authorization_error',
    })
  })

  it('refuses a visitor who is not signed in', async () => {
    await expect(register(await firstOpenEventId())).rejects.toMatchObject({
      status: 401,
      code: 'authentication_error',
    })
  })

  it('answers 404 for an event that is not in the catalogue', async () => {
    signInAs(MOCK_CATALOGUE_TOKENS.ATTENDEE)

    await expect(register(99999)).rejects.toMatchObject({ status: 404, code: 'not_found' })
  })

  it('keeps each set of handlers separate, so one test cannot leak into another', async () => {
    signInAs(MOCK_CATALOGUE_TOKENS.ATTENDEE)
    const eventId = await firstOpenEventId()
    await register(eventId)
    server.use(...createCatalogueHandlers())

    const fresh = (await fetchPage()).items.find((item) => item.id === eventId)
    expect(fresh?.is_registered).toBe(false)
  })
})
