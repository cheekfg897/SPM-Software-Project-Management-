import type { BookingRequest, ReassessmentFlag } from '@/features/booking/api'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'

import type { Drift } from './flaggedBookingRules'

/** An event as the booking mock knows it: only what a booking request carries from the event. */
export interface MockBookingEvent {
  id: number
  reference: string
  /** For Venue Staff's list of events (SCRUM-24 AC4). */
  name: string
  coordinator_id: number
  status: 'approved' | 'safety_review' | 'confirmed'
  expected_attendance: number
  proposed_date: string
  end_date: string | null
  start_time: string
  end_time: string
  accessibility_needs: string | null
}

export interface MockBookingVenue {
  id: number
  capacity: number
}

const APPROVED_EVENT: MockBookingEvent = {
  id: 101,
  reference: 'EVR-BOOK0101',
  name: 'Partner Summit',
  coordinator_id: MOCK_ACCOUNTS.coordinator.id,
  status: 'approved',
  expected_attendance: 80,
  proposed_date: '2026-11-10',
  end_date: null,
  start_time: '09:00:00',
  end_time: '17:00:00',
  accessibility_needs: 'Step-free access',
}

/**
 * Eleven events: one the coordinator can book for, one already confirmed, one assigned
 * elsewhere, two whose requests are waiting for Venue Staff (SCRUM-43), two of the
 * coordinator's with several venue arrangements already decided (SCRUM-93), two whose
 * arrangements reached the later statuses (Released, Expired, On hold), one the Safety Officer
 * has approved, whose booking Venue Staff are preparing (SCRUM-84), and one in Safety Review
 * whose venue was deactivated (SCRUM-92). The waiting two run on different dates, so the queue's
 * order is visible.
 */
export const MOCK_BOOKING_EVENTS = {
  approved: APPROVED_EVENT,
  confirmed: { ...APPROVED_EVENT, id: 102, reference: 'EVR-BOOK0102', status: 'confirmed' },
  someoneElses: { ...APPROVED_EVENT, id: 103, reference: 'EVR-BOOK0103', coordinator_id: 999 },
  laterShowcase: {
    ...APPROVED_EVENT,
    id: 104,
    reference: 'EVR-BOOK0104',
    name: 'Product Showcase',
    proposed_date: '2026-12-01',
    start_time: '10:00:00',
  },
  earlierWorkshop: {
    ...APPROVED_EVENT,
    id: 105,
    reference: 'EVR-BOOK0105',
    name: 'Design Workshop',
    proposed_date: '2026-11-20',
  },
  multiVenue: {
    ...APPROVED_EVENT,
    id: 106,
    reference: 'EVR-BOOK0106',
    proposed_date: '2026-11-25',
  },
  booked: {
    ...APPROVED_EVENT,
    id: 107,
    reference: 'EVR-BOOK0107',
    proposed_date: '2026-11-26',
  },
  replaced: {
    ...APPROVED_EVENT,
    id: 108,
    reference: 'EVR-BOOK0108',
    proposed_date: '2026-11-27',
  },
  held: {
    ...APPROVED_EVENT,
    id: 109,
    reference: 'EVR-BOOK0109',
    proposed_date: '2026-11-28',
  },
  safetyApproved: {
    ...APPROVED_EVENT,
    id: 110,
    reference: 'EVR-BOOK0110',
    proposed_date: '2026-11-12',
  },
  inSafetyReview: {
    ...APPROVED_EVENT,
    id: 111,
    reference: 'EVR-BOOK0111',
    name: 'Charity Gala',
    status: 'safety_review',
    proposed_date: '2026-11-29',
  },
  /**
   * Confirmed, with two venues booked and one withdrawn, for what its organiser sees (SCRUM-24
   * AC10). Marcus coordinates it (an id no mock account has), so no coordinator page lists it.
   */
  confirmedGala: {
    ...APPROVED_EVENT,
    id: 112,
    reference: 'EVR-BOOK0112',
    name: 'Harbour Gala',
    coordinator_id: 99,
    status: 'confirmed',
    proposed_date: '2026-12-05',
    start_time: '17:00:00',
    end_time: '23:00:00',
  },
  /**
   * Moved a day later, from 15 to 16 November, and up from 80 to 120 people since its venues were
   * booked, so a change flagged them for Venue Staff to reconfirm or reject (SCRUM-59).
   */
  moved: {
    ...APPROVED_EVENT,
    id: 113,
    reference: 'EVR-BOOK0113',
    name: 'Moved Conference',
    expected_attendance: 120,
    proposed_date: '2026-11-16',
  },
} as const satisfies Record<string, MockBookingEvent>

/**
 * The events the Safety Officer has approved, so their bookings' preparation can be recorded
 * (SCRUM-84 AC5). Every other event, the booked one included, is still waiting.
 */
export const MOCK_SAFETY_APPROVED_EVENT_IDS: readonly number[] = [
  MOCK_BOOKING_EVENTS.safetyApproved.id,
]

/** One venue that fits the approved event's 80 guests and one that does not. */
export const MOCK_BOOKING_VENUES = {
  roomy: { id: 1, capacity: 200 },
  tiny: { id: 2, capacity: 20 },
} as const satisfies Record<string, MockBookingVenue>

/**
 * The requests waiting for a decision when a test starts, raised in the opposite order
 * to the one the queue shows them in: the backend orders by the event's date, not by id.
 */
export const MOCK_PENDING_DECISIONS = [
  {
    id: 9002,
    event_id: MOCK_BOOKING_EVENTS.laterShowcase.id,
    venue_id: 2,
    starts_at: '2026-12-01T10:00:00+08:00',
    ends_at: '2026-12-01T16:00:00+08:00',
    purpose: 'Main hall',
    expected_occupancy: 150,
    required_layout: 'theatre',
    justification: null,
    status: 'pending',
    decision_reason: null,
    suggested_venue_id: null,
    suggested_starts_at: null,
    suggested_ends_at: null,
    preparation_status: 'not_started',
    preparation_notes: null,
    hold_expires_at: null,
    needs_alternative_venue: false,
    unavailability: [],
    replaces_request_id: null,
    flagged_after_change: false,
    reassessment_flags: [],
    event_proposed_date: MOCK_BOOKING_EVENTS.laterShowcase.proposed_date,
    event_end_date: MOCK_BOOKING_EVENTS.laterShowcase.end_date,
    event_start_time: MOCK_BOOKING_EVENTS.laterShowcase.start_time,
    event_end_time: MOCK_BOOKING_EVENTS.laterShowcase.end_time,
    accessibility_needs: MOCK_BOOKING_EVENTS.laterShowcase.accessibility_needs,
  },
  {
    id: 9001,
    event_id: MOCK_BOOKING_EVENTS.earlierWorkshop.id,
    venue_id: 1,
    starts_at: '2026-11-20T09:00:00+08:00',
    ends_at: '2026-11-20T12:00:00+08:00',
    purpose: 'Breakout room',
    expected_occupancy: 40,
    required_layout: 'classroom',
    justification: null,
    status: 'pending',
    decision_reason: null,
    suggested_venue_id: null,
    suggested_starts_at: null,
    suggested_ends_at: null,
    preparation_status: 'not_started',
    preparation_notes: null,
    hold_expires_at: null,
    needs_alternative_venue: false,
    unavailability: [],
    replaces_request_id: null,
    flagged_after_change: false,
    reassessment_flags: [],
    event_proposed_date: MOCK_BOOKING_EVENTS.earlierWorkshop.proposed_date,
    event_end_date: MOCK_BOOKING_EVENTS.earlierWorkshop.end_date,
    event_start_time: MOCK_BOOKING_EVENTS.earlierWorkshop.start_time,
    event_end_time: MOCK_BOOKING_EVENTS.earlierWorkshop.end_time,
    accessibility_needs: MOCK_BOOKING_EVENTS.earlierWorkshop.accessibility_needs,
  },
] as const satisfies readonly BookingRequest[]

/**
 * A decided or withdrawn arrangement of `event`: the event's own details, as the backend adds
 * them. A held or expired one also says when its hold runs or ran out, a flagged one why it
 * needs an alternative venue (SCRUM-92), and one being prepared how far that has got (SCRUM-84).
 */
function arrangementOf(
  event: MockBookingEvent,
  arrangement: Pick<
    BookingRequest,
    'id' | 'venue_id' | 'starts_at' | 'ends_at' | 'purpose' | 'status' | 'decision_reason'
  > &
    Partial<
      Pick<
        BookingRequest,
        | 'hold_expires_at'
        | 'needs_alternative_venue'
        | 'unavailability'
        | 'preparation_status'
        | 'preparation_notes'
        | 'required_layout'
        | 'expected_occupancy'
        | 'justification'
        | 'flagged_after_change'
        | 'reassessment_flags'
        | 'suggested_venue_id'
        | 'suggested_starts_at'
        | 'suggested_ends_at'
      >
    >,
): BookingRequest {
  return {
    suggested_venue_id: null,
    suggested_starts_at: null,
    suggested_ends_at: null,
    hold_expires_at: null,
    needs_alternative_venue: false,
    unavailability: [],
    preparation_status: 'not_started',
    preparation_notes: null,
    required_layout: null,
    expected_occupancy: 10,
    justification: null,
    flagged_after_change: false,
    reassessment_flags: [],
    ...arrangement,
    event_id: event.id,
    replaces_request_id: null,
    event_proposed_date: event.proposed_date,
    event_end_date: event.end_date,
    event_start_time: event.start_time,
    event_end_time: event.end_time,
    accessibility_needs: event.accessibility_needs,
  }
}

const TIMING_CHANGED_FLAG: ReassessmentFlag = {
  kind: 'requires_reconfirmation',
  reason: "The event's date or time changed.",
}
const ATTENDANCE_ROSE_FLAG: ReassessmentFlag = {
  kind: 'requires_reconfirmation',
  reason:
    "The event's expected attendance rose from 80 to 120, above this arrangement's expected occupancy of 80.",
}
const MOVED_A_DAY_LATER: Drift = {
  startMovedByMs: 24 * 60 * 60_000,
  endMovedByMs: 24 * 60 * 60_000,
  attendanceBefore: 80,
  attendanceNow: 120,
}

/**
 * Arrangements no longer waiting for Venue Staff, so the queue never shows them (SCRUM-93).
 * The multi-venue event has two rejected and one withdrawn; the booked event has an approved
 * one, which nothing can withdraw and whose venue has since been blocked, so it is flagged as
 * needing an alternative venue (SCRUM-92), and a rejected one. Each event's are saved out of period
 * order, and two start together, so the list's order (period, then id) is visible.
 *
 * The replaced event's original hall was released when its replacement was approved (SCRUM-92),
 * and its gallery hold ran out (SCRUM-94). The held event's studio is On hold (SCRUM-75), so the
 * Venue Staff queue lists it, waiting for final approval; its venue has since been blocked, so it
 * is flagged too, as the backend flags a hold (ADR-0100).
 *
 * The earlier workshop's exhibition hall is approved, which makes that event multi-venue, so its
 * Breakout room (9001, in the queue) can be held (SCRUM-75 AC1). It is at the other venue in the
 * afternoon, so it clashes with nothing.
 *
 * The safety-approved event's ballroom is approved and under way (SCRUM-84): Venue Staff can go
 * on preparing it, while the booked event's hall is refused until its safety approval.
 *
 * The venue of the event in Safety Review was deactivated, so its approved auditorium is flagged
 * with no end to the unavailability (SCRUM-92).
 *
 * The confirmed gala's dinner hall and reception room are approved, saved out of period order,
 * with Venue Staff's reasons and preparation, and its overflow room was withdrawn: its organiser
 * sees all three in full (SCRUM-24 AC10, ADR-0104).
 *
 * The moved event's arrangements were flagged when it moved a day later and grew to 120 people
 * (SCRUM-59): an approved plenary hall that held everyone and must be reconfirmed for 120, a
 * workshop room still waiting for a decision, an approved stage too small for 120, and an approved
 * annex whose venue has since been blocked, which only a replacement settles.
 */
export const MOCK_ARRANGEMENTS = {
  rejectedMain: arrangementOf(MOCK_BOOKING_EVENTS.multiVenue, {
    id: 9101,
    venue_id: MOCK_BOOKING_VENUES.roomy.id,
    starts_at: '2026-11-25T13:00:00+08:00',
    ends_at: '2026-11-25T17:00:00+08:00',
    purpose: 'Main programme',
    status: 'rejected',
    decision_reason: 'Hall closed for repairs',
  }),
  rejectedBreakout: arrangementOf(MOCK_BOOKING_EVENTS.multiVenue, {
    id: 9103,
    venue_id: MOCK_BOOKING_VENUES.tiny.id,
    starts_at: '2026-11-25T09:00:00+08:00',
    ends_at: '2026-11-25T11:00:00+08:00',
    purpose: 'Breakout session',
    status: 'rejected',
    decision_reason: 'Double-booked',
  }),
  withdrawnOverflow: arrangementOf(MOCK_BOOKING_EVENTS.multiVenue, {
    id: 9102,
    venue_id: MOCK_BOOKING_VENUES.roomy.id,
    starts_at: '2026-11-25T09:00:00+08:00',
    ends_at: '2026-11-25T12:00:00+08:00',
    purpose: 'Overflow room',
    status: 'withdrawn',
    decision_reason: null,
  }),
  bookedHall: arrangementOf(MOCK_BOOKING_EVENTS.booked, {
    id: 9104,
    venue_id: MOCK_BOOKING_VENUES.roomy.id,
    starts_at: '2026-11-26T13:00:00+08:00',
    ends_at: '2026-11-26T17:00:00+08:00',
    purpose: 'Main hall',
    status: 'approved',
    decision_reason: 'Booked',
    needs_alternative_venue: true,
    unavailability: [
      {
        category: 'maintenance',
        reason: 'Roof repairs',
        starts_at: '2026-11-26T08:00:00+08:00',
        ends_at: '2026-11-26T18:00:00+08:00',
      },
    ],
  }),
  bookedSideRoom: arrangementOf(MOCK_BOOKING_EVENTS.booked, {
    id: 9105,
    venue_id: MOCK_BOOKING_VENUES.tiny.id,
    starts_at: '2026-11-26T09:00:00+08:00',
    ends_at: '2026-11-26T11:00:00+08:00',
    purpose: 'Side room',
    status: 'rejected',
    decision_reason: 'Too small',
  }),
  releasedHall: arrangementOf(MOCK_BOOKING_EVENTS.replaced, {
    id: 9106,
    venue_id: MOCK_BOOKING_VENUES.roomy.id,
    starts_at: '2026-11-27T09:00:00+08:00',
    ends_at: '2026-11-27T12:00:00+08:00',
    purpose: 'Original hall',
    status: 'released',
    decision_reason: 'Booked',
  }),
  expiredGallery: arrangementOf(MOCK_BOOKING_EVENTS.replaced, {
    id: 9107,
    venue_id: MOCK_BOOKING_VENUES.tiny.id,
    starts_at: '2026-11-27T13:00:00+08:00',
    ends_at: '2026-11-27T15:00:00+08:00',
    purpose: 'Gallery',
    status: 'expired',
    decision_reason: null,
    hold_expires_at: '2026-11-20T09:00:00+08:00',
  }),
  heldStudio: arrangementOf(MOCK_BOOKING_EVENTS.held, {
    id: 9108,
    venue_id: MOCK_BOOKING_VENUES.roomy.id,
    starts_at: '2026-11-28T09:00:00+08:00',
    ends_at: '2026-11-28T12:00:00+08:00',
    purpose: 'Studio',
    status: 'on_hold',
    decision_reason: null,
    hold_expires_at: '2026-11-21T09:00:00+08:00',
    needs_alternative_venue: true,
    unavailability: [
      {
        category: 'safety_concern',
        reason: 'Ceiling leak',
        starts_at: '2026-11-28T08:00:00+08:00',
        ends_at: '2026-11-28T13:00:00+08:00',
      },
    ],
  }),
  exhibitionHall: arrangementOf(MOCK_BOOKING_EVENTS.earlierWorkshop, {
    id: 9003,
    venue_id: MOCK_BOOKING_VENUES.tiny.id,
    starts_at: '2026-11-20T13:00:00+08:00',
    ends_at: '2026-11-20T16:00:00+08:00',
    purpose: 'Exhibition hall',
    status: 'approved',
    decision_reason: 'Booked',
  }),
  preparedBallroom: arrangementOf(MOCK_BOOKING_EVENTS.safetyApproved, {
    id: 9109,
    venue_id: MOCK_BOOKING_VENUES.roomy.id,
    starts_at: '2026-11-12T09:00:00+08:00',
    ends_at: '2026-11-12T17:00:00+08:00',
    purpose: 'Grand ballroom',
    status: 'approved',
    decision_reason: 'Booked',
    preparation_status: 'in_progress',
    preparation_notes: 'Stage half built.',
  }),
  reviewedAuditorium: arrangementOf(MOCK_BOOKING_EVENTS.inSafetyReview, {
    id: 9110,
    venue_id: MOCK_BOOKING_VENUES.roomy.id,
    starts_at: '2026-11-29T09:00:00+08:00',
    ends_at: '2026-11-29T17:00:00+08:00',
    purpose: 'Auditorium',
    status: 'approved',
    decision_reason: 'Booked',
    needs_alternative_venue: true,
    unavailability: [
      {
        category: 'renovation',
        reason: 'Closed for refit',
        starts_at: '2026-11-01T12:00:00+08:00',
        ends_at: null,
      },
    ],
  }),
  galaDinner: arrangementOf(MOCK_BOOKING_EVENTS.confirmedGala, {
    id: 9111,
    venue_id: MOCK_BOOKING_VENUES.roomy.id,
    starts_at: '2026-12-05T18:00:00+08:00',
    ends_at: '2026-12-05T23:00:00+08:00',
    purpose: 'Gala dinner',
    required_layout: 'banquet',
    status: 'approved',
    decision_reason: 'Booked for the dinner.',
    preparation_status: 'ready',
    preparation_notes: 'Tables set for 80.',
  }),
  galaReception: arrangementOf(MOCK_BOOKING_EVENTS.confirmedGala, {
    id: 9112,
    venue_id: MOCK_BOOKING_VENUES.tiny.id,
    starts_at: '2026-12-05T17:00:00+08:00',
    ends_at: '2026-12-05T18:00:00+08:00',
    purpose: 'Drinks reception',
    status: 'approved',
    decision_reason: 'Booked',
  }),
  galaOverflow: arrangementOf(MOCK_BOOKING_EVENTS.confirmedGala, {
    id: 9113,
    venue_id: MOCK_BOOKING_VENUES.tiny.id,
    starts_at: '2026-12-05T19:00:00+08:00',
    ends_at: '2026-12-05T21:00:00+08:00',
    purpose: 'Overflow room',
    status: 'withdrawn',
    decision_reason: null,
  }),
  movedHall: arrangementOf(MOCK_BOOKING_EVENTS.moved, {
    id: 9114,
    venue_id: MOCK_BOOKING_VENUES.roomy.id,
    starts_at: '2026-11-15T09:00:00+08:00',
    ends_at: '2026-11-15T12:00:00+08:00',
    purpose: 'Plenary hall',
    status: 'approved',
    decision_reason: 'Booked',
    expected_occupancy: 80,
    flagged_after_change: true,
    reassessment_flags: [TIMING_CHANGED_FLAG, ATTENDANCE_ROSE_FLAG],
  }),
  movedWorkshop: arrangementOf(MOCK_BOOKING_EVENTS.moved, {
    id: 9115,
    venue_id: MOCK_BOOKING_VENUES.tiny.id,
    starts_at: '2026-11-15T13:00:00+08:00',
    ends_at: '2026-11-15T15:00:00+08:00',
    purpose: 'Workshop room',
    status: 'pending',
    decision_reason: null,
    flagged_after_change: true,
    reassessment_flags: [TIMING_CHANGED_FLAG],
  }),
  movedStage: arrangementOf(MOCK_BOOKING_EVENTS.moved, {
    id: 9116,
    venue_id: MOCK_BOOKING_VENUES.tiny.id,
    starts_at: '2026-11-15T15:30:00+08:00',
    ends_at: '2026-11-15T17:00:00+08:00',
    purpose: 'Stage',
    status: 'approved',
    decision_reason: 'Booked',
    expected_occupancy: 80,
    justification: 'Standing only.',
    flagged_after_change: true,
    reassessment_flags: [
      TIMING_CHANGED_FLAG,
      {
        kind: 'no_longer_suitable',
        reason: "Expected attendance of 120 exceeds the venue's capacity of 20.",
      },
    ],
  }),
  movedAnnex: arrangementOf(MOCK_BOOKING_EVENTS.moved, {
    id: 9117,
    venue_id: MOCK_BOOKING_VENUES.roomy.id,
    starts_at: '2026-11-15T13:00:00+08:00',
    ends_at: '2026-11-15T14:00:00+08:00',
    purpose: 'Annex',
    status: 'approved',
    decision_reason: 'Booked',
    needs_alternative_venue: true,
    unavailability: [
      {
        category: 'maintenance',
        reason: 'Floor sanding',
        starts_at: '2026-11-15T12:00:00+08:00',
        ends_at: '2026-11-15T18:00:00+08:00',
      },
    ],
    flagged_after_change: true,
    reassessment_flags: [TIMING_CHANGED_FLAG],
  }),
} as const satisfies Record<string, BookingRequest>

/**
 * What changed under each flagged arrangement of the moved event since it was booked: the event's
 * start moved a day later and its attendance rose from 80 to 120 (SCRUM-59, `Drift`).
 */
export const MOCK_FLAGGED_DRIFTS: Readonly<Record<number, Drift>> = {
  [MOCK_ARRANGEMENTS.movedHall.id]: MOVED_A_DAY_LATER,
  [MOCK_ARRANGEMENTS.movedWorkshop.id]: MOVED_A_DAY_LATER,
  [MOCK_ARRANGEMENTS.movedStage.id]: MOVED_A_DAY_LATER,
  [MOCK_ARRANGEMENTS.movedAnnex.id]: MOVED_A_DAY_LATER,
}
