import { fetchCatalogue, registerForEvent } from '@/features/catalogue/api'
import type { CataloguePage } from '@/features/catalogue/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'

/**
 * SCRUM-52: the catalogue against the real backend (docs/adr/0032-event-catalogue-contract.md).
 *
 * Nothing in the API can confirm an event yet (SCRUM-49) or enable registration on one without
 * it, so a fresh backend lists no events. These tests check everything the backend answers with
 * no event to list: the page's shape, paging, every refusal. The checks that need a listed event
 * wait below as todos, and become real tests once an event can be confirmed. The mock handlers
 * stand in for them until then.
 */

const CATALOGUE_PATH = '/api/events/catalogue'
const DEFAULT_PAGE_SIZE = 12
/** An id no event has, so registering for it is a 404. */
const MISSING_EVENT_ID = 2_000_000_000
const NOT_PERMITTED_MESSAGE = 'You do not have permission to perform this action.'
const EVENT_NOT_FOUND_MESSAGE = 'Event not found.'
const PRESET_OR_RANGE_MESSAGE = 'Send either a preset or a custom range, not both.'
const PRESETS_MESSAGE = 'Must be one of: upcoming, today, this_week, this_weekend.'

/** Every field the frontend's CatalogueEvent type reads, and nothing more. */
const CATALOGUE_EVENT_FIELDS = [
  'capacity',
  'description',
  'ends_at',
  'id',
  'is_full',
  'is_registered',
  'name',
  'places_left',
  'reference',
  'starts_at',
  'venue',
].sort()

afterEach(() => sendRequestsAs(null))

describe('SCRUM-52 event catalogue contract (ADR-0032)', () => {
  it('answers a visitor with a page in exactly the shape the frontend reads', async () => {
    const page = await fetchCatalogue({})

    expect(Object.keys(page).sort()).toEqual(['items', 'page', 'page_size', 'total', 'total_pages'])
    expect(page).toMatchObject({ page: 1, page_size: DEFAULT_PAGE_SIZE })
    expect(page.items.length).toBeLessThanOrEqual(DEFAULT_PAGE_SIZE)
    for (const item of page.items) {
      expect(Object.keys(item).sort()).toEqual(CATALOGUE_EVENT_FIELDS)
    }
  })

  it('pages with page, page_size, total and total_pages, and a default page size of 12', async () => {
    const withDefaults = await fetchCatalogue({})
    const withSmallPages = await apiRequest<CataloguePage>(CATALOGUE_PATH, {
      query: { page: '2', page_size: '5' },
    })

    expect(withDefaults.page_size).toBe(DEFAULT_PAGE_SIZE)
    expect(withDefaults.total_pages).toBe(Math.ceil(withDefaults.total / DEFAULT_PAGE_SIZE))
    expect(withSmallPages).toMatchObject({ page: 2, page_size: 5 })
    expect(withSmallPages.total_pages).toBe(Math.ceil(withSmallPages.total / 5))
  })

  it('answers a page past the last one with no items and the real totals', async () => {
    const first = await fetchCatalogue({})
    const pastTheEnd = first.total_pages + 1

    const page = await fetchCatalogue({ page: String(pastTheEnd) })

    expect(page.items).toEqual([])
    expect(page).toMatchObject({
      page: pastTheEnd,
      total: first.total,
      total_pages: first.total_pages,
    })
  })

  it('refuses a range that ends before it starts with a validation error on starts_to', async () => {
    const error = await refusal(
      fetchCatalogue({ starts_from: '2026-10-20T12:00', starts_to: '2026-10-20T11:00' }),
    )

    expect(error).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { starts_to: ['Must be after starts_from.'] },
    })
  })

  it('refuses when together with a custom range, and an unknown when', async () => {
    const both = await refusal(fetchCatalogue({ when: 'today', starts_from: '2026-10-20T00:00' }))
    const unknown = await refusal(fetchCatalogue({ when: 'someday' }))

    expect(both).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { when: [PRESET_OR_RANGE_MESSAGE] },
    })
    expect(unknown).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { when: [PRESETS_MESSAGE] },
    })
  })

  it('refuses registering without a token (401) or as another role (403)', async () => {
    const visitor = await refusal(registerForEvent(MISSING_EVENT_ID))
    await signInAs(staffAccount())
    const coordinator = await refusal(registerForEvent(MISSING_EVENT_ID))

    expect(visitor).toMatchObject({ status: 401, code: 'authentication_error' })
    expect(coordinator).toMatchObject({
      status: 403,
      code: 'authorization_error',
      message: NOT_PERMITTED_MESSAGE,
    })
  })

  it('answers 404 for an event that is not open for registration', async () => {
    await signInAsNewAttendee()

    const error = await refusal(registerForEvent(MISSING_EVENT_ID))

    expect(error).toMatchObject({
      status: 404,
      code: 'not_found',
      message: EVENT_NOT_FOUND_MESSAGE,
    })
  })

  // These need an event that is confirmed with registration enabled, which nothing can make yet.
  it.todo('lists only confirmed events with registration enabled, soonest first, without a token')
  it.todo('searches name and description with q, ignoring case (and venue name, once it exists)')
  it.todo('resolves when=today, this_week and this_weekend in business time')
  it.todo('filters by starts_from and starts_to, reading a time without an offset as business time')
  it.todo('sets is_registered for the signed-in attendee and false for a visitor')
  it.todo('registers an attendee (201) and counts the place in places_left')
  it.todo(
    'refuses a second registration (409 already_registered) and a full event (409 event_full)',
  )
})
