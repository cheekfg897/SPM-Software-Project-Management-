import type { BookingRequestStatus, ReassessmentFlag } from '@/features/booking/api'

/**
 * How a significant change to an event reassesses each of its venue arrangements (SCRUM-33 AC6,
 * ADR-0094), as `flag_arrangements_after_change` in venue/services.py does it, for the edit mock
 * to flag both the booking mock's arrangements and the ones the planning gates count.
 */

const TIMING_CHANGED_REASON = "The event's date or time changed."
const VENUE_REQUIREMENTS_CHANGED_REASON = "The event's venue requirements changed."

/** The statuses a change can flag: an arrangement still holding or asking for its venue. */
export const FLAGGABLE_STATUSES: readonly BookingRequestStatus[] = [
  'pending',
  'conflicting',
  'approved',
]

/** What a significant change did to the event, as its arrangements see it (SignificantChange). */
export interface SignificantChange {
  timingChanged: boolean
  venueRequirementsChanged: boolean
  /** The expected attendance before and after the change; equal when it didn't change. */
  previousAttendance: number
  newAttendance: number
  /** How far the change moved the event's start, in milliseconds; 0 when it didn't (SCRUM-59). */
  startMovedByMs: number
}

/** What reassessing an arrangement reads: its own expected occupancy and its venue's capacity. */
export interface ArrangementSize {
  expectedOccupancy: number
  venueCapacity: number
}

/**
 * Whether an arrangement that held the whole audience no longer does (`_outgrown`): its occupancy
 * covered the attendance before, and the attendance is now above it.
 */
export function isOutgrown(occupancy: number, attendanceBefore: number, attendanceNow: number) {
  return occupancy >= attendanceBefore && attendanceNow > occupancy
}

/**
 * The flag an attendance change leaves, if any (`_attendance_flag`): only an arrangement that held
 * everyone before the change and is now outgrown. It is no longer suitable when its venue can't
 * hold the new attendance, and otherwise needs reconfirming for the larger audience.
 */
function attendanceFlag(size: ArrangementSize, change: SignificantChange): ReassessmentFlag | null {
  if (!isOutgrown(size.expectedOccupancy, change.previousAttendance, change.newAttendance)) {
    return null
  }
  if (change.newAttendance > size.venueCapacity) {
    return {
      kind: 'no_longer_suitable',
      reason: `Expected attendance of ${change.newAttendance} exceeds the venue's capacity of ${size.venueCapacity}.`,
    }
  }
  return {
    kind: 'requires_reconfirmation',
    reason:
      `The event's expected attendance rose from ${change.previousAttendance} to ` +
      `${change.newAttendance}, above this arrangement's expected occupancy of ${size.expectedOccupancy}.`,
  }
}

/** Each reason `change` gives to flag an arrangement, in the backend's order; empty for none. */
export function reassessmentFlagsFor(
  size: ArrangementSize,
  change: SignificantChange,
): ReassessmentFlag[] {
  const flags: ReassessmentFlag[] = []
  if (change.timingChanged) {
    flags.push({ kind: 'requires_reconfirmation', reason: TIMING_CHANGED_REASON })
  }
  if (change.venueRequirementsChanged) {
    flags.push({ kind: 'requires_reconfirmation', reason: VENUE_REQUIREMENTS_CHANGED_REASON })
  }
  const attendance = attendanceFlag(size, change)
  if (attendance !== null) {
    flags.push(attendance)
  }
  return flags
}

/** One Safety Review or confirmation gap per flag, as `_venue_gaps` words it (SCRUM-58 AC3). */
export function flaggedGaps(arrangementId: number, flags: readonly ReassessmentFlag[]): string[] {
  return flags.map(
    (flag) =>
      `Venue arrangement ${arrangementId} is flagged (${flag.kind.replaceAll('_', ' ')}): ${flag.reason}`,
  )
}
