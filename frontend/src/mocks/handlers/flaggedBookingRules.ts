import type { BookingRequest, Reconfirmation } from '@/features/booking/api'
import type { FieldErrors } from '@/lib/api'

import { isOutgrown } from './reassessmentRules'
import type { SignificantChange } from './reassessmentRules'
import { instantField } from './venueBlockRules'
import { unknownFieldErrors } from './venueRules'

/**
 * How Venue Staff reconfirm or reject a booking a change flagged (SCRUM-59, ADR-0112), as
 * venue/services.py and ReconfirmBookingSchema check it, for the booking mock.
 */

/** Business time is UTC+8 all year (BUSINESS_UTC_OFFSET), as milliseconds. */
const BUSINESS_OFFSET_MS = 8 * 60 * 60_000
const NOT_A_STRING_MESSAGE = 'Not a valid string.'
/** The fields ReconfirmBookingSchema declares; the reject payload has only the reason. */
const RECONFIRM_FIELDS: readonly string[] = ['starts_at', 'ends_at', 'reason']
const REJECT_FIELDS: readonly string[] = ['reason']

/** The backend's refusals (venue/services.py, SCRUM-59). */
export const NOT_FLAGGED_AFTER_CHANGE_MESSAGE =
  'This booking is not flagged after a change, so there is nothing to reconfirm or reject.'
export const SETTLED_BY_REPLACEMENT_MESSAGE =
  'This booking needs an alternative venue, which only a replacement settles.'

/** An instant as the backend's messages write it, in business time: "2026-11-16 09:00". */
export function noticeTime(instant: number): string {
  return new Date(instant + BUSINESS_OFFSET_MS).toISOString().slice(0, 16).replace('T', ' ')
}

/** An instant as the backend sends it, in business time: "2026-11-16T09:00:00+08:00". */
export function businessIso(instant: number): string {
  return `${new Date(instant + BUSINESS_OFFSET_MS).toISOString().slice(0, 19)}+08:00`
}

/**
 * What changed under a booking since its period was last set, raised or reconfirmed: how far the
 * event's start moved, and the attendance before the first change and now. The backend reads it
 * back from the event's history (get_event_when_arranged); the mock keeps it as the edits arrive.
 */
export interface Drift {
  startMovedByMs: number
  attendanceBefore: number
  attendanceNow: number
}

/** The drift once `change` is added to what was there before, if anything. */
export function driftAfter(before: Drift | undefined, change: SignificantChange): Drift {
  if (before === undefined) {
    return {
      startMovedByMs: change.startMovedByMs,
      attendanceBefore: change.previousAttendance,
      attendanceNow: change.newAttendance,
    }
  }
  return {
    startMovedByMs: before.startMovedByMs + change.startMovedByMs,
    attendanceBefore: before.attendanceBefore,
    attendanceNow: change.newAttendance,
  }
}

/**
 * What reconfirming the booking gives it (`_reconfirmation_of`): its period moved by as much as the
 * event's start moved (AC2), and the attendance now as its occupancy when it held everyone and was
 * outgrown (AC10). With no drift, nothing has moved.
 */
export function reconfirmationOf(
  booking: BookingRequest,
  drift: Drift | undefined,
): Reconfirmation {
  const movedBy = drift?.startMovedByMs ?? 0
  let occupancy = booking.expected_occupancy
  if (drift !== undefined && isOutgrown(occupancy, drift.attendanceBefore, drift.attendanceNow)) {
    occupancy = drift.attendanceNow
  }
  return {
    starts_at: businessIso(Date.parse(booking.starts_at) + movedBy),
    ends_at: businessIso(Date.parse(booking.ends_at) + movedBy),
    expected_occupancy: occupancy,
  }
}

/**
 * The reason's own message: present, it must be text. Null counts as no reason, since the schema's
 * `load_default=None` lets it through (FlaggedBookingReasonSchema).
 */
function reasonFieldErrors(body: Record<string, unknown>): FieldErrors {
  if (body.reason === undefined || body.reason === null) {
    return {}
  }
  return typeof body.reason === 'string' ? {} : { reason: [NOT_A_STRING_MESSAGE] }
}

/** What ReconfirmBookingSchema refuses: an unknown field, a bad time or reason, or ends first. */
export function reconfirmErrors(body: Record<string, unknown>): FieldErrors {
  const errors = unknownFieldErrors(body, RECONFIRM_FIELDS)
  const starts = instantField(body, 'starts_at', errors)
  const ends = instantField(body, 'ends_at', errors)
  Object.assign(errors, reasonFieldErrors(body))
  if (Object.keys(errors).length > 0 || starts === null || ends === null) {
    return errors
  }
  return ends <= starts ? { ends_at: ['ends_at must be after starts_at.'] } : {}
}

/** What the reject payload refuses: an unknown field, or a reason that isn't text. */
export function rejectErrors(body: Record<string, unknown>): FieldErrors {
  return { ...unknownFieldErrors(body, REJECT_FIELDS), ...reasonFieldErrors(body) }
}

/** The reason sent, trimmed; a blank one counts as missing (AC4). */
export function reasonOf(body: Record<string, unknown>): string | null {
  if (typeof body.reason !== 'string' || body.reason.trim() === '') {
    return null
  }
  return body.reason.trim()
}

/** When the booking's event starts and ends, as milliseconds, from the booking's event fields. */
function eventSpan(booking: BookingRequest): [number, number] {
  const endsOn = booking.event_end_date ?? booking.event_proposed_date
  return [
    Date.parse(`${booking.event_proposed_date}T${booking.event_start_time}+08:00`),
    Date.parse(`${endsOn}T${booking.event_end_time}+08:00`),
  ]
}

/** The backend's 400 details for a period outside the event (`_require_within_event`, AC2). */
export function outsideEventErrors(booking: BookingRequest, starts: number, ends: number) {
  const [eventStarts, eventEnds] = eventSpan(booking)
  const message = `The period must lie within the event's start and end: ${noticeTime(eventStarts)} to ${noticeTime(eventEnds)}.`
  const errors: FieldErrors = {}
  if (starts < eventStarts) {
    errors.starts_at = [message]
  }
  if (ends > eventEnds) {
    errors.ends_at = [message]
  }
  return errors
}

/** The backend's message when the venue is too small for the occupancy and no reason came (AC4). */
export function capacityReasonMessage(capacity: number, occupancy: number): string {
  return `A reason is required because the venue's capacity of ${String(capacity)} is below the booking's expected occupancy of ${String(occupancy)}.`
}
