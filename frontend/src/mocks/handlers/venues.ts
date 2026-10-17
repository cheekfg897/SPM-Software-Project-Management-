import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import type {
  BlockOverlapWarning,
  OpeningPeriod,
  OverlapWarning,
  Venue,
} from '@/features/venues/api'
import { WEEKDAYS } from '@/features/venues/constants'
import { isRecord } from '@/lib/isRecord'

import { errorResponse, notAllowed, notAuthenticated, validationError } from '../responses'

import { accountForRequest } from './auth'
import { MOCK_VENUE_BLOCKS, MOCK_VENUE_BOOKINGS, MOCK_VENUES } from './venueFixtures'
import type { MockVenueBlock, MockVenueBooking } from './venueFixtures'
import { newVenueErrors, venueChangeErrors } from './venueRules'

/**
 * The venue catalogue routes (SCRUM-25, SCRUM-67), answering as backend/app/modules/venue/
 * routes.py does: anyone signed in reads, only Venue Staff write, the body is checked before the
 * venue is looked for, and a change to setup or turnaround reports what now overlaps (ADR-0033).
 */

const VENUES_PATH = '/api/venues'
const VENUE_PATH = `${VENUES_PATH}/:venueId`
const VENUE_NOT_FOUND_MESSAGE = 'Venue not found.'
const NOT_AN_OBJECT_MESSAGE = 'Request body must be a JSON object.'
/** DEFAULT_VENUE_SETUP_MINUTES and DEFAULT_VENUE_TURNAROUND_MINUTES (config.py, ADR-0011). */
const STANDARD_BUFFER_MINUTES = 30
const MINUTE_MS = 60_000
const BUSINESS_OFFSET_MS = 8 * 60 * MINUTE_MS
const FIRST_NEW_VENUE_ID = 900

let venues: Venue[] = []
let bookings: MockVenueBooking[] = []
let blocks: MockVenueBlock[] = []
let nextVenueId = FIRST_NEW_VENUE_ID

/** Put the venues, bookings and blocks back as they started. Runs after every test. */
export function resetMockVenues(): void {
  venues = Object.values(MOCK_VENUES).map((venue) => structuredClone(venue))
  bookings = MOCK_VENUE_BOOKINGS.map((booking) => ({ ...booking }))
  blocks = MOCK_VENUE_BLOCKS.map((block) => ({ ...block }))
  nextVenueId = FIRST_NEW_VENUE_ID
}

resetMockVenues()

/** Anyone signed in may read a venue; otherwise the response to send. */
function checkSignedIn(request: Request) {
  return accountForRequest(request) === undefined ? notAuthenticated() : null
}

/** Only Venue Staff may change the catalogue; otherwise the response to send. */
function checkVenueStaff(request: Request) {
  const user = accountForRequest(request)
  if (user === undefined) {
    return notAuthenticated()
  }
  return user.role === ROLE.VENUE_STAFF ? null : notAllowed()
}

function findVenue(venueId: unknown): Venue | undefined {
  return venues.find((venue) => venue.id === Number(venueId))
}

function venueNotFound() {
  return errorResponse(404, 'not_found', VENUE_NOT_FOUND_MESSAGE)
}

/** The JSON body as an object, or null for anything else (load_or_raise refuses it). */
async function readObject(request: Request): Promise<Record<string, unknown> | null> {
  const body: unknown = await request.json().catch(() => null)
  return isRecord(body) ? body : null
}

function byName(left: Venue, right: Venue): number {
  if (left.name === right.name) {
    return 0
  }
  return left.name < right.name ? -1 : 1
}

const DAY_ORDER: readonly string[] = WEEKDAYS.map((weekday) => weekday.value)

/** The schedule in week order, as VenueSchema.get_opening_hours sorts it. */
function inWeekOrder(periods: OpeningPeriod[]): OpeningPeriod[] {
  return [...periods].sort(
    (left, right) =>
      DAY_ORDER.indexOf(left.open.day) - DAY_ORDER.indexOf(right.open.day) ||
      left.open.time.localeCompare(right.open.time),
  )
}

/** Every day 09:00 to 18:00: what a venue created without hours gets (ADR-0008). */
function standardHours(): OpeningPeriod[] {
  return WEEKDAYS.map(({ value }) => ({
    open: { day: value, time: '09:00' },
    close: { day: value, time: '18:00' },
  }))
}

/** A list item as the backend stores it: trimmed and lower case. */
function normalisedItems(items: unknown): string[] {
  // Only called on a body the rules accepted, where every item is text.
  return (items as string[]).map((item) => item.trim().toLowerCase())
}

/** The fields sent, applied to `venue` the way the backend's schema normalises them. */
function applyChanges(venue: Venue, body: Record<string, unknown>): Venue {
  // The rules accepted the body, so each field present has the type its key says.
  const changes = body as Partial<Venue>
  const updated: Venue = { ...venue, ...changes }
  if (changes.name !== undefined) {
    updated.name = changes.name.trim()
  }
  if (changes.location !== undefined) {
    updated.location = changes.location.trim()
  }
  if (changes.facilities !== undefined) {
    updated.facilities = normalisedItems(changes.facilities)
  }
  if (changes.accessibility_features !== undefined) {
    updated.accessibility_features = normalisedItems(changes.accessibility_features)
  }
  updated.opening_hours = inWeekOrder(updated.opening_hours)
  return updated
}

/** A moment as the backend writes it, in business time: `2026-11-10T12:30:00+08:00`. */
function businessIso(ms: number): string {
  return `${new Date(ms + BUSINESS_OFFSET_MS).toISOString().slice(0, 19)}+08:00`
}

/** The period a booking holds its venue, padded by setup and turnaround (ADR-0011). */
function heldPeriod(venue: Venue, booking: MockVenueBooking): [number, number] {
  return [
    Date.parse(booking.start_time) - venue.setup_minutes * MINUTE_MS,
    Date.parse(booking.end_time) + venue.turnaround_minutes * MINUTE_MS,
  ]
}

/** The time two periods share, or null when they only touch or are apart. */
function sharedPeriod(
  [firstStart, firstEnd]: [number, number],
  [secondStart, secondEnd]: [number, number],
): [string, string] | null {
  const start = Math.max(firstStart, secondStart)
  const end = Math.min(firstEnd, secondEnd)
  return start < end ? [businessIso(start), businessIso(end)] : null
}

function byStartThenId(
  left: { id: number; start_time: string },
  right: { id: number; start_time: string },
): number {
  return Date.parse(left.start_time) - Date.parse(right.start_time) || left.id - right.id
}

function confirmedBookingsOf(venue: Venue): MockVenueBooking[] {
  return bookings
    .filter((booking) => booking.venue_id === venue.id && booking.status === 'confirmed')
    .sort(byStartThenId)
}

/** Each pair of the venue's confirmed bookings whose padded periods overlap. */
function bookingOverlaps(venue: Venue): OverlapWarning[] {
  const confirmed = confirmedBookingsOf(venue)
  const warnings: OverlapWarning[] = []
  confirmed.forEach((first, index) => {
    for (const second of confirmed.slice(index + 1)) {
      const shared = sharedPeriod(heldPeriod(venue, first), heldPeriod(venue, second))
      if (shared !== null) {
        const [overlap_start, overlap_end] = shared
        warnings.push({ booking_ids: [first.id, second.id], overlap_start, overlap_end })
      }
    }
  })
  return warnings
}

/** Each of the venue's confirmed bookings whose padded period runs into one of its blocks. */
function blockOverlaps(venue: Venue): BlockOverlapWarning[] {
  const venueBlocks = blocks.filter((block) => block.venue_id === venue.id).sort(byStartThenId)
  const warnings: BlockOverlapWarning[] = []
  for (const booking of confirmedBookingsOf(venue)) {
    for (const block of venueBlocks) {
      const blocked: [number, number] = [Date.parse(block.start_time), Date.parse(block.end_time)]
      const shared = sharedPeriod(heldPeriod(venue, booking), blocked)
      if (shared !== null) {
        const [overlap_start, overlap_end] = shared
        warnings.push({ booking_id: booking.id, block_id: block.id, overlap_start, overlap_end })
      }
    }
  }
  return warnings
}

/** Setting `is_active` on a venue, for the deactivate and reactivate routes. */
function setActive(isActive: boolean) {
  return ({ request, params }: { request: Request; params: Record<string, unknown> }) => {
    const refusal = checkVenueStaff(request)
    if (refusal !== null) {
      return refusal
    }
    const venue = findVenue(params.venueId)
    if (venue === undefined) {
      return venueNotFound()
    }
    venue.is_active = isActive
    return HttpResponse.json(venue)
  }
}

export const venueHandlers: RequestHandler[] = [
  http.get(VENUES_PATH, ({ request }) => {
    const refusal = checkSignedIn(request)
    return refusal ?? HttpResponse.json(venues.filter((venue) => venue.is_active).sort(byName))
  }),

  http.post(VENUES_PATH, async ({ request }) => {
    const refusal = checkVenueStaff(request)
    if (refusal !== null) {
      return refusal
    }
    const body = await readObject(request)
    if (body === null) {
      return errorResponse(400, 'validation_error', NOT_AN_OBJECT_MESSAGE)
    }
    const errors = newVenueErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }

    const blank: Venue = {
      id: nextVenueId,
      name: '',
      location: '',
      capacity: 0,
      facilities: [],
      accessibility_features: [],
      supported_layouts: [],
      opening_hours: standardHours(),
      setup_minutes: STANDARD_BUFFER_MINUTES,
      turnaround_minutes: STANDARD_BUFFER_MINUTES,
      is_active: true,
    }
    const created = applyChanges(blank, body)
    nextVenueId += 1
    venues.push(created)
    return HttpResponse.json(created, { status: 201 })
  }),

  http.get(VENUE_PATH, ({ request, params }) => {
    const refusal = checkSignedIn(request)
    if (refusal !== null) {
      return refusal
    }
    const venue = findVenue(params.venueId)
    return venue === undefined ? venueNotFound() : HttpResponse.json(venue)
  }),

  http.patch(VENUE_PATH, async ({ request, params }) => {
    const refusal = checkVenueStaff(request)
    if (refusal !== null) {
      return refusal
    }
    const body = await readObject(request)
    if (body === null) {
      return errorResponse(400, 'validation_error', NOT_AN_OBJECT_MESSAGE)
    }
    const errors = venueChangeErrors(body)
    if (Object.keys(errors).length > 0) {
      return validationError(errors)
    }
    const venue = findVenue(params.venueId)
    if (venue === undefined) {
      return venueNotFound()
    }

    const updated = applyChanges(venue, body)
    venues = venues.map((existing) => (existing.id === updated.id ? updated : existing))
    const buffersChanged =
      updated.setup_minutes !== venue.setup_minutes ||
      updated.turnaround_minutes !== venue.turnaround_minutes
    return HttpResponse.json({
      ...updated,
      overlap_warnings: buffersChanged ? bookingOverlaps(updated) : [],
      block_overlap_warnings: buffersChanged ? blockOverlaps(updated) : [],
    })
  }),

  http.post(`${VENUE_PATH}/deactivate`, setActive(false)),
  http.post(`${VENUE_PATH}/reactivate`, setActive(true)),
]
