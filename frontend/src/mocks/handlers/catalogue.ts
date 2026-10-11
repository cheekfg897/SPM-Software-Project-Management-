import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import { WHEN } from '@/features/catalogue/constants'
import type { FieldErrors } from '@/lib/api'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'
import { errorResponse, notAllowed, notAuthenticated, validationError } from '../responses'

import { accountForRequest } from './auth'

import {
  addDays,
  MOCK_ATTENDEE_REGISTRATIONS,
  MOCK_CATALOGUE_EVENTS,
  MOCK_NOW,
  MOCK_TODAY,
} from './catalogueFixtures'
import type { MockCatalogueEvent } from './catalogueFixtures'

/**
 * The event catalogue endpoints as docs/adr/0032-event-catalogue-contract.md describes them.
 * This stands in for SCRUM-52's backend, so the searching, date windows, paging and counting
 * happen here, never in the UI.
 */

const CATALOGUE_PATH = '/api/events/catalogue'
const DEFAULT_PAGE_SIZE = 12
const MAX_PAGE_SIZE = 50
const KNOWN_WHEN: readonly string[] = Object.values(WHEN)
/** A date-time as the browser's datetime-local input sends it, with optional seconds and offset. */
const DATE_TIME_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})?$/
const OFFSET_PATTERN = /(Z|[+-]\d{2}:\d{2})$/

interface CatalogueQuery {
  q: string
  when: string
  startsFrom: string | null
  startsTo: string | null
  page: number
  pageSize: number
}

/** A date-time as business time to the minute ("2026-10-05T19:30"), comparable as text. */
function toBusinessMinute(value: string): string {
  if (!OFFSET_PATTERN.test(value)) {
    return value.slice(0, 16)
  }
  const shifted = new Date(new Date(value).getTime() + 8 * 60 * 60_000)
  return shifted.toISOString().slice(0, 16)
}

function readWholeNumber(value: string | null, fallback: number): number {
  return value === null ? fallback : Number(value)
}

function readQuery(url: URL): { query: CatalogueQuery; errors: FieldErrors } {
  const params = url.searchParams
  const query: CatalogueQuery = {
    q: (params.get('q') ?? '').trim().toLowerCase(),
    when: params.get('when') ?? WHEN.UPCOMING,
    startsFrom: params.get('starts_from'),
    startsTo: params.get('starts_to'),
    page: readWholeNumber(params.get('page'), 1),
    pageSize: readWholeNumber(params.get('page_size'), DEFAULT_PAGE_SIZE),
  }

  const errors: FieldErrors = {}
  const hasRange = query.startsFrom !== null || query.startsTo !== null
  if (!KNOWN_WHEN.includes(query.when)) {
    errors.when = [`Must be one of: ${KNOWN_WHEN.join(', ')}.`]
  } else if (hasRange && params.has('when')) {
    errors.when = ['Send either a preset or a custom range, not both.']
  }
  for (const [name, value] of [
    ['starts_from', query.startsFrom],
    ['starts_to', query.startsTo],
  ] as const) {
    if (value !== null && !DATE_TIME_PATTERN.test(value)) {
      errors[name] = ['Not a valid date-time.']
    }
  }
  const bothValid =
    query.startsFrom !== null && query.startsTo !== null && !errors.starts_from && !errors.starts_to
  if (
    bothValid &&
    toBusinessMinute(query.startsTo ?? '') < toBusinessMinute(query.startsFrom ?? '')
  ) {
    errors.starts_to = ['Must be after starts_from.']
  }
  if (!Number.isInteger(query.page) || query.page < 1) {
    errors.page = ['Must be at least 1.']
  }
  if (!Number.isInteger(query.pageSize) || query.pageSize < 1 || query.pageSize > MAX_PAGE_SIZE) {
    errors.page_size = [`Must be between 1 and ${MAX_PAGE_SIZE}.`]
  }
  return { query, errors }
}

/** The business dates a preset covers, first and last inclusive; null means no limit. */
function presetDates(when: string): { first: string; last: string } | null {
  // MOCK_TODAY is a Monday, so the week runs to +6 and the weekend is +5 and +6.
  if (when === WHEN.TODAY) {
    return { first: MOCK_TODAY, last: MOCK_TODAY }
  }
  if (when === WHEN.THIS_WEEK) {
    return { first: MOCK_TODAY, last: addDays(MOCK_TODAY, 6) }
  }
  if (when === WHEN.THIS_WEEKEND) {
    return { first: addDays(MOCK_TODAY, 5), last: addDays(MOCK_TODAY, 6) }
  }
  return null
}

function matchesQuery(event: MockCatalogueEvent, query: CatalogueQuery): boolean {
  const hasEnded = new Date(event.ends_at) <= new Date(MOCK_NOW)
  if (hasEnded) {
    return false
  }

  const searchable = `${event.name} ${event.description} ${event.venue?.name ?? ''}`.toLowerCase()
  if (!searchable.includes(query.q)) {
    return false
  }

  const startMinute = event.starts_at.slice(0, 16)
  const startDate = startMinute.slice(0, 10)
  const dates = presetDates(query.when)
  if (dates !== null && (startDate < dates.first || startDate > dates.last)) {
    return false
  }
  if (query.startsFrom !== null && startMinute < toBusinessMinute(query.startsFrom)) {
    return false
  }
  if (query.startsTo !== null && startMinute > toBusinessMinute(query.startsTo)) {
    return false
  }
  return true
}

/** Who has registered for each event: event id to user ids. */
const registrations = new Map<number, Set<number>>()
let lastRegistrationId = 0

function registeredUsers(eventId: number): Set<number> {
  const users = registrations.get(eventId) ?? new Set<number>()
  registrations.set(eventId, users)
  return users
}

/** Forget every registration made since, keeping the fixture's own. Runs after every test. */
export function resetMockCatalogue(): void {
  registrations.clear()
  lastRegistrationId = 0
  for (const eventId of MOCK_ATTENDEE_REGISTRATIONS) {
    registeredUsers(eventId).add(MOCK_ACCOUNTS.attendee.id)
  }
}
resetMockCatalogue()

function toItem(event: MockCatalogueEvent, userId: number | null) {
  const { taken, ...fields } = event
  const users = registeredUsers(event.id)
  const placesLeft = Math.max(event.capacity - taken - users.size, 0)
  return {
    ...fields,
    places_left: placesLeft,
    is_full: placesLeft === 0,
    is_registered: userId !== null && users.has(userId),
  }
}

export const catalogueHandlers: RequestHandler[] = [
  http.get(CATALOGUE_PATH, ({ request }) => {
    const { query, errors } = readQuery(new URL(request.url))
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }

    const user = accountForRequest(request)
    const matching = MOCK_CATALOGUE_EVENTS.filter((event) => matchesQuery(event, query)).sort(
      (first, second) => first.starts_at.localeCompare(second.starts_at),
    )
    const start = (query.page - 1) * query.pageSize
    return HttpResponse.json({
      items: matching
        .slice(start, start + query.pageSize)
        .map((event) => toItem(event, user?.id ?? null)),
      page: query.page,
      page_size: query.pageSize,
      total: matching.length,
      total_pages: Math.ceil(matching.length / query.pageSize),
    })
  }),

  http.post(`${CATALOGUE_PATH}/:eventId/registrations`, ({ request, params }) => {
    const user = accountForRequest(request)
    if (user === undefined) {
      return notAuthenticated()
    }
    if (user.role !== ROLE.ATTENDEE) {
      return notAllowed()
    }

    const event = MOCK_CATALOGUE_EVENTS.find((candidate) => String(candidate.id) === params.eventId)
    if (event === undefined) {
      return errorResponse(404, 'not_found', 'Event not found.')
    }
    const item = toItem(event, user.id)
    if (item.is_registered) {
      return errorResponse(409, 'already_registered', 'You are already registered for this event.')
    }
    if (item.is_full) {
      return errorResponse(409, 'event_full', 'This event is full.')
    }

    registeredUsers(event.id).add(user.id)
    lastRegistrationId += 1
    return HttpResponse.json(
      {
        id: lastRegistrationId,
        event_id: event.id,
        status: 'registered',
        registered_at: MOCK_NOW,
      },
      { status: 201 },
    )
  }),
]
