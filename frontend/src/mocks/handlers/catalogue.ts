import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import { MY_EVENTS_WHEN, WHEN } from '@/features/catalogue/constants'
import type { FieldErrors } from '@/lib/api'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'
import { errorResponse, notAllowed, notAuthenticated, validationError } from '../responses'

import { accountForRequest } from './auth'

import {
  addDays,
  MOCK_ATTENDEE_REGISTRATIONS,
  MOCK_ATTENDEE_UNLISTED_EVENTS,
  MOCK_CATALOGUE_EVENTS,
  MOCK_NOW,
  MOCK_TODAY,
} from './catalogueFixtures'
import type { MockCatalogueEvent, MockUnlistedEvent } from './catalogueFixtures'

/**
 * The event catalogue endpoints as docs/adr/0032-event-catalogue-contract.md describes them,
 * and an Attendee's own events as docs/adr/0044-attendee-events-list.md does. This stands in
 * for SCRUM-52's and SCRUM-24's backend, so the searching, date windows, paging, counting and
 * the upcoming and past split happen here, never in the UI.
 */

const CATALOGUE_PATH = '/api/events/catalogue'
const MY_EVENTS_PATH = '/api/events/registrations'
const KNOWN_MY_EVENTS_WHEN: readonly string[] = Object.values(MY_EVENTS_WHEN)
/** What an empty half of an Attendee's events says, as the backend words it. */
const NO_MY_EVENTS_MESSAGE: Record<string, string> = {
  [MY_EVENTS_WHEN.UPCOMING]: 'You have no upcoming events.',
  [MY_EVENTS_WHEN.PAST]: 'You have no past events.',
}
const DEFAULT_PAGE_SIZE = 12
const MAX_PAGE_SIZE = 50
const KNOWN_WHEN: readonly string[] = Object.values(WHEN)
/** Every query parameter the backend reads; any other is refused as an unknown field. */
const KNOWN_PARAMS: readonly string[] = [
  'q',
  'when',
  'starts_from',
  'starts_to',
  'page',
  'page_size',
]
const NOT_AN_INTEGER_MESSAGE = 'Not a valid integer.'
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

/** The backend's message for a query number that isn't a whole number, or is out of range. */
function integerErrors(value: number, isInRange: boolean, rangeMessage: string): string[] | null {
  if (!Number.isInteger(value)) {
    return [NOT_AN_INTEGER_MESSAGE]
  }
  return isInRange ? null : [rangeMessage]
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
  const pageErrors = integerErrors(query.page, query.page >= 1, 'Must be at least 1.')
  if (pageErrors !== null) {
    errors.page = pageErrors
  }
  const pageSizeErrors = integerErrors(
    query.pageSize,
    query.pageSize >= 1 && query.pageSize <= MAX_PAGE_SIZE,
    `Must be between 1 and ${MAX_PAGE_SIZE}.`,
  )
  if (pageSizeErrors !== null) {
    errors.page_size = pageSizeErrors
  }
  for (const name of params.keys()) {
    if (!KNOWN_PARAMS.includes(name)) {
      errors[name] = ['Unknown field.']
    }
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

/** One row of an Attendee's events, as the backend sends it. */
interface MyEventRow {
  event_id: number
  name: string
  starts_at: string
  ends_at: string
  event_status: string
  status: 'registered' | 'withdrawn'
  registered_at: string
  withdrawn_at: string | null
}

function myEventRow(
  event: MockCatalogueEvent | MockUnlistedEvent,
  eventStatus: string,
): MyEventRow {
  return {
    event_id: event.id,
    name: event.name,
    starts_at: event.starts_at,
    ends_at: event.ends_at,
    event_status: eventStatus,
    status: 'registered',
    registered_at: MOCK_NOW,
    withdrawn_at: null,
  }
}

/** Every event `userId` registered for, in no particular order. */
function myEventRows(userId: number): MyEventRow[] {
  const rows: MyEventRow[] = []
  for (const event of MOCK_CATALOGUE_EVENTS) {
    if (registeredUsers(event.id).has(userId)) {
      rows.push(myEventRow(event, 'confirmed'))
    }
  }
  if (userId === MOCK_ACCOUNTS.attendee.id) {
    for (const event of MOCK_ATTENDEE_UNLISTED_EVENTS) {
      rows.push(myEventRow(event, event.event_status))
    }
  }
  return rows
}

/** Soonest start first, then by event id, as the backend orders upcoming events. */
function bySoonestStart(first: MyEventRow, second: MyEventRow): number {
  return first.starts_at.localeCompare(second.starts_at) || first.event_id - second.event_id
}

/** The backend's 400s for an Attendee's events: an unknown window or parameter. */
function myEventsQueryErrors(params: URLSearchParams, when: string): FieldErrors {
  const errors: FieldErrors = {}
  if (!KNOWN_MY_EVENTS_WHEN.includes(when)) {
    errors.when = [`Must be one of: ${KNOWN_MY_EVENTS_WHEN.join(', ')}.`]
  }
  for (const name of params.keys()) {
    if (name !== 'when') {
      errors[name] = ['Unknown field.']
    }
  }
  return errors
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
        withdrawn_at: null,
      },
      { status: 201 },
    )
  }),

  http.get(MY_EVENTS_PATH, ({ request }) => {
    const user = accountForRequest(request)
    if (user === undefined) {
      return notAuthenticated()
    }
    if (user.role !== ROLE.ATTENDEE) {
      return notAllowed()
    }
    const params = new URL(request.url).searchParams
    const when = params.get('when') ?? MY_EVENTS_WHEN.UPCOMING
    const errors = myEventsQueryErrors(params, when)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }

    const now = new Date(MOCK_NOW)
    const rows = myEventRows(user.id).sort(bySoonestStart)
    const upcoming = rows.filter((row) => new Date(row.ends_at) > now)
    const past = rows.filter((row) => new Date(row.ends_at) <= now).reverse()
    const registrations = when === MY_EVENTS_WHEN.PAST ? past : upcoming
    if (registrations.length === 0) {
      return HttpResponse.json({ registrations, message: NO_MY_EVENTS_MESSAGE[when] })
    }
    return HttpResponse.json({ registrations })
  }),
]
