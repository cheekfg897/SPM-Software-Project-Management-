import { UNAVAILABILITY_CATEGORIES } from '@/config/unavailabilityCategories'
import { VENUE_LAYOUTS } from '@/config/venueLayouts'
import { WEEKDAYS } from '@/features/venues/constants'
import type { FieldErrors } from '@/lib/api'
import { isRecord } from '@/lib/isRecord'

/**
 * The backend's checks on a venue (EditVenueSchema in backend/app/modules/venue/schemas.py and
 * the opening-hours rules in opening_hours.py, ADR-0008), worded as marshmallow words them. A new
 * venue needs a name, a location and a capacity; a change checks only the fields it sends. A day
 * or time left out of a period is refused as an invalid one, where the backend would call it
 * missing: the web app always sends both.
 */

export const MISSING_MESSAGE = 'Missing data for required field.'
const NULL_MESSAGE = 'Field may not be null.'
const NOT_INTEGER_MESSAGE = 'Not a valid integer.'
const NOT_LIST_MESSAGE = 'Not a valid list.'
const TEXT_MAX_LENGTH = 200
const LIST_ITEM_MAX_LENGTH = 50
/** What fits the 500-character column: n items of 50 and n - 1 commas (models.py). */
const LIST_MAX_ITEMS = 9
const LIST_SEPARATOR = ','
const MINUTES_PER_DAY = 24 * 60
const MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY

const LAYOUT_VALUES: readonly string[] = VENUE_LAYOUTS.map((layout) => layout.value)
const DAY_VALUES: readonly string[] = WEEKDAYS.map((weekday) => weekday.value)

/** Every field a venue's payload may carry; anything else is an unknown field. */
const VENUE_FIELDS: readonly string[] = [
  'name',
  'location',
  'capacity',
  'facilities',
  'accessibility_features',
  'supported_layouts',
  'setup_minutes',
  'turnaround_minutes',
  'opening_hours',
]

const REQUIRED_FIELDS = ['name', 'location', 'capacity'] as const

function oneOfMessage(values: readonly string[]): string {
  return `Must be one of: ${values.join(', ')}.`
}

function textErrors(value: unknown, label: string): string[] {
  if (value === null) {
    return [NULL_MESSAGE]
  }
  if (typeof value !== 'string') {
    return ['Not a valid string.']
  }
  const messages: string[] = []
  if (value.trim() === '') {
    messages.push('Must not be blank.')
  }
  if (value.length > TEXT_MAX_LENGTH) {
    messages.push(`${label} must be at most ${TEXT_MAX_LENGTH} characters.`)
  }
  return messages
}

/** An integer at or above `minimum`, or the messages marshmallow gives instead. */
function integerErrors(value: unknown, minimum: number, tooSmall: string): string[] {
  if (value === null) {
    return [NULL_MESSAGE]
  }
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    return [NOT_INTEGER_MESSAGE]
  }
  return value < minimum ? [tooSmall] : []
}

function listItemErrors(item: unknown): string[] {
  if (typeof item !== 'string') {
    return ['Not a valid string.']
  }
  const messages: string[] = []
  if (item.trim() === '') {
    messages.push('Items cannot be blank.')
  }
  if (item.includes(LIST_SEPARATOR)) {
    messages.push(`Items cannot contain "${LIST_SEPARATOR}".`)
  }
  if (item.length > LIST_ITEM_MAX_LENGTH) {
    messages.push(`Items must be at most ${LIST_ITEM_MAX_LENGTH} characters.`)
  }
  return messages
}

function layoutErrors(item: unknown): string[] {
  return typeof item === 'string' && LAYOUT_VALUES.includes(item)
    ? []
    : [oneOfMessage(LAYOUT_VALUES)]
}

/** How long a list may be, and what the backend says when it is longer. */
interface ListLimit {
  limit: number
  message: string
}

const ITEMS_LIMIT: ListLimit = {
  limit: LIST_MAX_ITEMS,
  message: `At most ${LIST_MAX_ITEMS} items are allowed.`,
}
const LAYOUTS_LIMIT: ListLimit = {
  limit: LAYOUT_VALUES.length,
  message: `At most ${LAYOUT_VALUES.length} layouts are allowed.`,
}

/**
 * A list field's messages: one key per refused item (`facilities.1`), or the field's own key for
 * the list as a whole. As in marshmallow, the length is only checked once every item passes.
 */
function listErrors(
  field: string,
  value: unknown,
  itemErrors: (item: unknown) => string[],
  tooMany: ListLimit,
): FieldErrors {
  if (!Array.isArray(value)) {
    return { [field]: [NOT_LIST_MESSAGE] }
  }
  const errors: FieldErrors = {}
  value.forEach((item: unknown, index) => {
    const messages = itemErrors(item)
    if (messages.length > 0) {
      errors[`${field}.${index}`] = messages
    }
  })
  if (Object.keys(errors).length === 0 && value.length > tooMany.limit) {
    errors[field] = [tooMany.message]
  }
  return errors
}

/** A checked opening period: day numbers (Monday 0) and minutes past midnight. */
interface CheckedPeriod {
  openDay: number
  opens: number
  closeDay: number
  closes: number
}

function minutesOf(time: unknown): number | null {
  const match = typeof time === 'string' ? /^(\d{1,2}):(\d{2})$/.exec(time) : null
  if (match === null) {
    return null
  }
  const hours = Number(match[1])
  const minutes = Number(match[2])
  return hours < 24 && minutes < 60 ? hours * 60 + minutes : null
}

/** One end of a period (`open` or `close`): its day and minutes, or its messages under `path`. */
function checkDayTime(end: unknown, path: string, errors: FieldErrors) {
  const fields = isRecord(end) ? end : {}
  const day = DAY_VALUES.indexOf(String(fields.day))
  const minutes = minutesOf(fields.time)
  if (day === -1) {
    errors[`${path}.day`] = [oneOfMessage(DAY_VALUES)]
  }
  if (minutes === null) {
    errors[`${path}.time`] = ['Not a valid time.']
  }
  return day === -1 || minutes === null ? null : { day, minutes }
}

/** Why a period isn't a valid opening period, or null if it is (period_error, ADR-0008). */
function periodError({ openDay, opens, closeDay, closes }: CheckedPeriod): string | null {
  const dayGap = (closeDay - openDay + 7) % 7
  if (dayGap === 0) {
    return closes <= opens
      ? 'Close time must be after open time. For hours past midnight, set the close day to the next day.'
      : null
  }
  if (dayGap === 1) {
    return closes > opens ? 'An opening period cannot be longer than 24 hours.' : null
  }
  return 'Close day must be the same day as the open day or the day after.'
}

/** Each period as minute ranges inside the week; Sunday into Monday becomes two (_week_pieces). */
function weekPieces(periods: CheckedPeriod[]): [number, number, number][] {
  const pieces: [number, number, number][] = []
  periods.forEach((checked, index) => {
    const dayGap = (checked.closeDay - checked.openDay + 7) % 7
    const start = checked.openDay * MINUTES_PER_DAY + checked.opens
    const end = checked.openDay * MINUTES_PER_DAY + dayGap * MINUTES_PER_DAY + checked.closes
    if (end > MINUTES_PER_WEEK) {
      pieces.push([start, MINUTES_PER_WEEK, index], [0, end - MINUTES_PER_WEEK, index])
    } else {
      pieces.push([start, end, index])
    }
  })
  return pieces
}

/** The positions of two overlapping periods, lower first, or null (find_overlap). */
function findOverlap(periods: CheckedPeriod[]): [number, number] | null {
  const pieces = weekPieces(periods).sort(
    (left, right) => left[0] - right[0] || left[1] - right[1] || left[2] - right[2],
  )
  let furthestEnd = -1
  let furthestIndex = -1
  for (const [start, end, index] of pieces) {
    // Touching isn't overlapping: a period may open the minute the one before it closes.
    if (start < furthestEnd) {
      return [Math.min(furthestIndex, index), Math.max(furthestIndex, index)]
    }
    furthestEnd = end
    furthestIndex = index
  }
  return null
}

function openingHoursErrors(value: unknown): FieldErrors {
  if (!Array.isArray(value)) {
    return { opening_hours: [NOT_LIST_MESSAGE] }
  }
  const errors: FieldErrors = {}
  const periods: CheckedPeriod[] = []
  value.forEach((item: unknown, index) => {
    const path = `opening_hours.${index}`
    const fields = isRecord(item) ? item : {}
    const open = checkDayTime(fields.open, `${path}.open`, errors)
    const close = checkDayTime(fields.close, `${path}.close`, errors)
    if (open === null || close === null) {
      return
    }
    const checked = {
      openDay: open.day,
      opens: open.minutes,
      closeDay: close.day,
      closes: close.minutes,
    }
    const error = periodError(checked)
    if (error === null) {
      periods.push(checked)
    } else {
      errors[`${path}.close`] = [error]
    }
  })
  // As in the backend, overlaps are only looked for once every period is valid.
  if (Object.keys(errors).length > 0) {
    return errors
  }
  const overlap = findOverlap(periods)
  if (overlap === null) {
    return errors
  }
  const [first, second] = overlap
  return { [`opening_hours.${second}`]: [`Overlaps opening period ${first}.`] }
}

function addMessages(errors: FieldErrors, field: string, messages: string[]) {
  if (messages.length > 0) {
    errors[field] = messages
  }
}

/** What changing a venue is refused for: each field it sends is checked on its own. */
export function venueChangeErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  for (const field of Object.keys(body)) {
    if (!VENUE_FIELDS.includes(field)) {
      errors[field] = ['Unknown field.']
    }
  }
  if ('name' in body) {
    addMessages(errors, 'name', textErrors(body.name, 'Name'))
  }
  if ('location' in body) {
    addMessages(errors, 'location', textErrors(body.location, 'Location'))
  }
  if ('capacity' in body) {
    addMessages(
      errors,
      'capacity',
      integerErrors(body.capacity, 1, 'Capacity must be a positive number.'),
    )
  }
  if ('setup_minutes' in body) {
    addMessages(
      errors,
      'setup_minutes',
      integerErrors(body.setup_minutes, 0, 'Setup time cannot be negative.'),
    )
  }
  if ('turnaround_minutes' in body) {
    addMessages(
      errors,
      'turnaround_minutes',
      integerErrors(body.turnaround_minutes, 0, 'Turnaround time cannot be negative.'),
    )
  }
  for (const field of ['facilities', 'accessibility_features'] as const) {
    if (field in body) {
      Object.assign(errors, listErrors(field, body[field], listItemErrors, ITEMS_LIMIT))
    }
  }
  if ('supported_layouts' in body) {
    Object.assign(
      errors,
      listErrors('supported_layouts', body.supported_layouts, layoutErrors, LAYOUTS_LIMIT),
    )
  }
  if ('opening_hours' in body) {
    Object.assign(errors, openingHoursErrors(body.opening_hours))
  }
  return errors
}

/** What creating a venue is refused for: a required field left out, or a bad field. */
export function newVenueErrors(body: Record<string, unknown>): FieldErrors {
  const errors = venueChangeErrors(body)
  for (const field of REQUIRED_FIELDS) {
    if (!(field in body)) {
      errors[field] = [MISSING_MESSAGE]
    }
  }
  return errors
}

/*
 * Deactivating (UnavailabilitySchema in venue/schemas.py, SCRUM-92 AC9, ADR-0053): a category
 * and a note, both required. Marshmallow's Enum field calls anything that isn't one of the
 * values unknown, whatever its type, and the note is measured once trimmed.
 */

const CATEGORY_VALUES: readonly string[] = UNAVAILABILITY_CATEGORIES.map(
  (category) => category.value,
)
const CATEGORY_UNKNOWN_MESSAGE =
  'Category must be one of maintenance, equipment_failure, renovation, safety_concern or other.'
const REASON_MAX_LENGTH = 500
const DEACTIVATION_FIELDS: readonly string[] = ['category', 'reason']

function categoryErrors(value: unknown): string[] {
  if (value === null) {
    return [NULL_MESSAGE]
  }
  return typeof value === 'string' && CATEGORY_VALUES.includes(value)
    ? []
    : [CATEGORY_UNKNOWN_MESSAGE]
}

function reasonErrors(value: unknown): string[] {
  if (value === null) {
    return [NULL_MESSAGE]
  }
  if (typeof value !== 'string') {
    return ['Not a valid string.']
  }
  if (value.trim() === '') {
    return ['Must not be blank.']
  }
  if (value.trim().length > REASON_MAX_LENGTH) {
    return [`Reason must be at most ${REASON_MAX_LENGTH} characters.`]
  }
  return []
}

/** What deactivating a venue is refused for: a field left out, a bad one, or an unknown one. */
export function deactivationErrors(body: Record<string, unknown>): FieldErrors {
  const errors: FieldErrors = {}
  for (const field of Object.keys(body)) {
    if (!DEACTIVATION_FIELDS.includes(field)) {
      errors[field] = ['Unknown field.']
    }
  }
  if ('category' in body) {
    addMessages(errors, 'category', categoryErrors(body.category))
  } else {
    errors.category = [MISSING_MESSAGE]
  }
  if ('reason' in body) {
    addMessages(errors, 'reason', reasonErrors(body.reason))
  } else {
    errors.reason = [MISSING_MESSAGE]
  }
  return errors
}
