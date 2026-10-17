import type { FieldErrors } from '@/lib/api'

import { MOCK_VENUE_BLOCKS, MOCK_VENUE_BOOKINGS } from './venueSearchFixtures'
import type { MockSearchVenue, MockVenuePeriod } from './venueSearchFixtures'

/**
 * The venue module's rules for search (SCRUM-35) and the suitability check (SCRUM-36), as
 * backend/app/modules/venue/schemas.py and services.py apply them, messages included.
 */

const MISSING_MESSAGE = 'Missing data for required field.'
const LAYOUTS = ['classroom', 'theatre', 'boardroom', 'banquet', 'exhibition', 'other']
const LIST_SEPARATOR = ','
const LIST_ITEM_MAX_LENGTH = 50
/** How many items fit the venue's 500-character column (LIST_MAX_ITEMS in venue/models.py). */
const LIST_MAX_ITEMS = 9
const REQUIREMENT_LISTS = ['required_facilities', 'required_accessibility'] as const

/** What an event asks of a venue, trimmed and lower case as the backend compares them. */
export interface MockRequirements {
  layout: string | null
  facilities: string[]
  accessibility: string[]
}

/** One requirement a venue fails, as the backend names it. */
export interface MockUnmetRequirement {
  requirement: 'capacity' | 'facilities' | 'accessibility' | 'layout'
  message: string
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is string => typeof item === 'string')
}

/** Every message for one list item: marshmallow runs each of its validators. */
function itemMessages(item: string): string[] {
  const messages: string[] = []
  if (item.trim() === '') {
    messages.push('Items cannot be blank.')
  } else if (item.includes(LIST_SEPARATOR)) {
    messages.push(`Items cannot contain "${LIST_SEPARATOR}".`)
  }
  if (item.length > LIST_ITEM_MAX_LENGTH) {
    messages.push(`Items must be at most ${LIST_ITEM_MAX_LENGTH} characters.`)
  }
  return messages
}

/** One list's messages: too many items, or each bad item keyed by its place, as `name.2`. */
function listErrors(name: string, items: string[]): FieldErrors {
  if (items.length > LIST_MAX_ITEMS) {
    return { [name]: [`At most ${LIST_MAX_ITEMS} items are allowed.`] }
  }
  const errors: FieldErrors = {}
  items.forEach((item, index) => {
    const messages = itemMessages(item)
    if (messages.length > 0) {
      errors[`${name}.${index}`] = messages
    }
  })
  return errors
}

/** The layout and item checks search and the check share (`_RequirementsSchema`). */
export function requirementErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  const layout = body.required_layout
  const isKnownLayout = typeof layout === 'string' && LAYOUTS.includes(layout)
  if (layout !== undefined && layout !== null && !isKnownLayout) {
    errors.required_layout = [`Must be one of: ${LAYOUTS.join(', ')}.`]
  }
  for (const name of REQUIREMENT_LISTS) {
    Object.assign(errors, listErrors(name, stringList(body[name])))
  }
  return errors
}

/** A whole number of at least 1, or the message the backend gives for `name`. */
export function positiveNumberErrors(body: Record<string, unknown>, name: string): FieldErrors {
  const value = body[name]
  if (value === undefined) {
    return { [name]: [MISSING_MESSAGE] }
  }
  if (typeof value !== 'number' || value < 1) {
    return { [name]: [`${name} must be a positive number.`] }
  }
  return {}
}

function normalised(items: string[]): string[] {
  return items.map((item) => item.trim().toLowerCase())
}

export function requirementsFrom(body: Record<string, unknown>): MockRequirements {
  return {
    layout: typeof body.required_layout === 'string' ? body.required_layout : null,
    facilities: normalised(stringList(body.required_facilities)),
    accessibility: normalised(stringList(body.required_accessibility)),
  }
}

function missingItems(required: string[], offered: readonly string[]): string[] {
  return required.filter((item) => !offered.includes(item))
}

/** Each facility, accessibility or layout requirement the venue fails, in the backend's order. */
export function unmetRequirements(
  venue: MockSearchVenue,
  requirements: MockRequirements,
): MockUnmetRequirement[] {
  const unmet: MockUnmetRequirement[] = []
  for (const item of missingItems(requirements.facilities, venue.facilities)) {
    unmet.push({ requirement: 'facilities', message: `The venue does not offer ${item}.` })
  }
  for (const item of missingItems(requirements.accessibility, venue.accessibility_features)) {
    unmet.push({ requirement: 'accessibility', message: `The venue does not offer ${item}.` })
  }
  const layout = requirements.layout
  if (layout !== null && !venue.supported_layouts.includes(layout)) {
    unmet.push({
      requirement: 'layout',
      message: `The venue does not support the ${layout} layout.`,
    })
  }
  return unmet
}

/** An ISO date-time sent in the body, in milliseconds; NaN for anything else. */
export function instantOf(value: unknown): number {
  return typeof value === 'string' ? Date.parse(value) : Number.NaN
}

function periodFieldErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  for (const name of ['start_time', 'end_time']) {
    if (body[name] === undefined) {
      errors[name] = [MISSING_MESSAGE]
    } else if (Number.isNaN(instantOf(body[name]))) {
      errors[name] = ['Not a valid datetime.']
    }
  }
  return errors
}

function endsAfterStart(body: Record<string, unknown>): boolean {
  return instantOf(body.end_time) > instantOf(body.start_time)
}

/** The search's own checks: its period and minimum capacity, then the shared ones. */
export function searchErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {
    ...periodFieldErrors(body),
    ...positiveNumberErrors(body, 'min_capacity'),
    ...requirementErrors(body),
  }
  // Like marshmallow's schema validators, the end-after-start rule runs once every field is valid.
  if (Object.keys(errors).length === 0 && !endsAfterStart(body)) {
    errors.end_time = ['end_time must be after start_time.']
  }
  return errors
}

/** Whether `period` overlaps `start`-`end`; periods that only touch don't. */
function overlaps(period: MockVenuePeriod, start: number, end: number): boolean {
  return Date.parse(period.start_time) < end && Date.parse(period.end_time) > start
}

const MINUTE = 60_000

/**
 * Whether the venue is free from `start` to `end`: no block overlaps the period itself, and no
 * booking that wasn't cancelled comes within the venue's setup plus turnaround of it (ADR-0011).
 */
export function isFree(venue: MockSearchVenue, start: number, end: number): boolean {
  const gap = (venue.setup_minutes + venue.turnaround_minutes) * MINUTE
  const blocked = MOCK_VENUE_BLOCKS.some(
    (block) => block.venue_id === venue.id && overlaps(block, start, end),
  )
  const booked = MOCK_VENUE_BOOKINGS.some(
    (booking) =>
      booking.venue_id === venue.id &&
      booking.status !== 'cancelled' &&
      overlaps(booking, start - gap, end + gap),
  )
  return !blocked && !booked
}
