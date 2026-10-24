import { ROLE } from '@/config/roles'
import { register } from '@/features/auth/api'
import {
  decideBookingRequest,
  fetchBookingRequests,
  placeBookingHold,
  raiseBookingRequest,
  withdrawArrangement,
} from '@/features/booking/api'
import type { BookingRequest } from '@/features/booking/api'
import {
  addEquipmentLine,
  fetchEventEquipmentLines,
  recordEquipmentOutcome,
} from '@/features/equipment/api'
import {
  completeEvent,
  confirmEvent,
  decideEventRequest,
  editEventRequest,
  fetchEventRequest,
  rejectEvent,
  requestClarification,
  sendToSafetyReview,
  startEventRequestReview,
  submitEventRequest,
  updateRegistrationSettings,
} from '@/features/eventRequests/api'
import { assignCoordinator } from '@/features/lead/api'
import { fetchNotifications } from '@/features/notifications/api'
import { blockVenue, fetchVenueCalendar, removeVenueBlock } from '@/features/venues/api'
import type { CreatedBlock } from '@/features/venues/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, staffAccount, uniqueEmail, VALID_PASSWORD } from './backend'
import type { Credentials } from './backend'

/**
 * The coordinator's planning actions against the running backend: sending an event to safety
 * review (SCRUM-97, ADR-0047), confirming it (SCRUM-49, ADR-0051), its registration settings
 * (SCRUM-69, ADR-0043), marking it completed (SCRUM-68, ADR-0027) (ADR-0075) and rejecting it
 * during planning (SCRUM-49 AC9, AC10, ADR-0093), and what a closed event's equipment requests
 * then refuse (SCRUM-48 AC8). Also the decision a venue booking request locks (SCRUM-31 AC7,
 * ADR-0084), and the statuses the coordinator's edit is allowed in (SCRUM-33 AC8, ADR-0101).
 *
 * The refusals that need no event of the coordinator's run with the staff account every run has
 * (an Event Coordinator) and new organisers. An event of the coordinator's needs a Lead to assign
 * it, an approved venue needs Venue Staff, a safety approval needs a Safety Officer and an
 * equipment outcome needs Technical Support, so those checks read the accounts from
 * INTEGRATION_LEAD_*, INTEGRATION_VENUE_STAFF_*, INTEGRATION_SAFETY_OFFICER_* and
 * INTEGRATION_TECH_SUPPORT_* and skip without them. CI makes all four (frontend.yml).
 *
 * Replacing an approved venue that Venue Staff then block (SCRUM-92, ADR-0053) runs here too,
 * since it starts from the same settled event.
 */

const NOT_PERMITTED = {
  status: 403,
  code: 'authorization_error',
  message: 'You do not have permission to perform this action.',
}
const NOT_SIGNED_IN = { status: 401, code: 'authentication_error' }
const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event request not found.' }
/** Every field of the event request the actions answer with (EventRequestSchema). */
const EVENT_REQUEST_FIELDS = [
  'accessibility_needs',
  'created_at',
  'description',
  'end_date',
  'end_time',
  'equipment_requirements',
  'expected_attendance',
  'name',
  'proposed_date',
  'purpose',
  'reference',
  'registration_required',
  'start_time',
  'status',
  'venue_requirements',
]
const SAFETY_REVIEW_NOT_READY = {
  status: 409,
  code: 'safety_review_not_allowed',
  message:
    'The event can go to Safety Review once every venue arrangement is approved and every ' +
    'equipment request has an outcome from Technical Support.',
}

/** A staff account read from two variables, or null when either is unset. */
function optionalAccount(email: string | undefined, password: string | undefined) {
  if (email === undefined || email === '' || password === undefined || password === '') {
    return null
  }
  return { email, password }
}

const LEAD = optionalAccount(
  import.meta.env.INTEGRATION_LEAD_EMAIL,
  import.meta.env.INTEGRATION_LEAD_PASSWORD,
)
const VENUE_STAFF = optionalAccount(
  import.meta.env.INTEGRATION_VENUE_STAFF_EMAIL,
  import.meta.env.INTEGRATION_VENUE_STAFF_PASSWORD,
)
const SAFETY_OFFICER = optionalAccount(
  import.meta.env.INTEGRATION_SAFETY_OFFICER_EMAIL,
  import.meta.env.INTEGRATION_SAFETY_OFFICER_PASSWORD,
)
const TECH_SUPPORT = optionalAccount(
  import.meta.env.INTEGRATION_TECH_SUPPORT_EMAIL,
  import.meta.env.INTEGRATION_TECH_SUPPORT_PASSWORD,
)
const canAssign = LEAD !== null
const canApproveVenue = canAssign && VENUE_STAFF !== null
const canApproveSafety = canApproveVenue && SAFETY_OFFICER !== null
const canRecordOutcome = canAssign && TECH_SUPPORT !== null

/** The account, which the test's skip condition has already checked is set. */
function required(account: Credentials | null): Credentials {
  if (account === null) {
    throw new Error('This check needs an account that is not set; it should have been skipped.')
  }
  return account
}

/** A date `days` from now, as the backend reads dates ("2026-11-20"). */
function daysFromNow(days: number): string {
  return new Date(Date.now() + days * 24 * 60 * 60_000).toISOString().slice(0, 10)
}

const EVENT_DATE = daysFromNow(30)

/** As the staff account: record a client organisation and sign its organiser up. */
async function newOrganiser(): Promise<Credentials> {
  await signInAs(staffAccount())
  const organisation = await apiRequest<{ id: number }>('/api/organisations', {
    method: 'POST',
    body: {
      name: `Integration organisation ${uniqueEmail('organisation')}`,
      contact_name: 'Integration Contact',
      contact_email: uniqueEmail('contact'),
    },
  })
  const organiser = { email: uniqueEmail('organiser'), password: VALID_PASSWORD }
  await register({
    full_name: 'Integration Organiser',
    ...organiser,
    role: ROLE.EVENT_ORGANISER,
    organisation_id: organisation.id,
  })
  return organiser
}

/** An event made for these checks, and the organiser who submitted it. */
interface PlannedEvent {
  reference: string
  organiser: Credentials
}

/** A new organiser's submitted request, with no coordinator yet. Leaves the organiser signed in. */
async function submittedEvent(): Promise<PlannedEvent> {
  const organiser = await newOrganiser()
  await signInAs(organiser)
  const submitted = await submitEventRequest({
    name: 'Integration Planning',
    proposed_date: EVENT_DATE,
    end_date: EVENT_DATE,
    start_time: '09:00',
    end_time: '17:00',
    expected_attendance: 120,
  })
  return { reference: submitted.reference, organiser }
}

/** A submitted request the Lead has assigned to the staff account, signed in as it. */
async function assignedEvent(): Promise<PlannedEvent> {
  const event = await submittedEvent()
  await signInAs(required(LEAD))
  await assignCoordinator({ reference: event.reference, coordinator_email: staffAccount().email })
  await signInAs(staffAccount())
  return event
}

/** An event the staff account has approved, with nothing arranged yet, signed in as it. */
async function approvedEvent(): Promise<PlannedEvent> {
  const event = await assignedEvent()
  await startEventRequestReview(event.reference)
  await decideEventRequest(event.reference, { outcome: 'approved' })
  return event
}

/** As Venue Staff: a new venue, big enough for every event here. */
async function newVenue(): Promise<number> {
  await signInAs(required(VENUE_STAFF))
  const venue = await apiRequest<{ id: number }>('/api/venues', {
    method: 'POST',
    body: {
      name: `Integration Hall ${uniqueEmail('venue')}`,
      location: 'Level 1',
      capacity: 300,
      supported_layouts: ['theatre'],
      facilities: ['projector'],
      accessibility_features: ['wheelchair_access'],
    },
  })
  return venue.id
}

/** As the staff account: ask for a new venue for the morning of the event. Returns its id. */
async function raiseVenueRequest(reference: string): Promise<number> {
  const venueId = await newVenue()
  await signInAs(staffAccount())
  const booking = await raiseBookingRequest(reference, {
    venue_id: venueId,
    starts_at: `${EVENT_DATE}T09:00:00+08:00`,
    ends_at: `${EVENT_DATE}T12:00:00+08:00`,
    purpose: 'Integration planning',
  })
  return booking.id
}

/** A planned event with its one venue arrangement, which Venue Staff approved. */
interface SettledEvent extends PlannedEvent {
  bookingId: number
}

/** An approved event whose one venue Venue Staff approved: ready for safety review. */
async function settledEvent(): Promise<SettledEvent> {
  const event = await approvedEvent()
  const bookingId = await raiseVenueRequest(event.reference)
  await signInAs(required(VENUE_STAFF))
  await decideBookingRequest(bookingId, { outcome: 'approved' })
  await signInAs(staffAccount())
  return { ...event, bookingId }
}

/** As Technical Support: a new equipment type with ten units. Returns its id. */
async function newEquipmentType(): Promise<number> {
  await signInAs(required(TECH_SUPPORT))
  const equipmentType = await apiRequest<{ id: number }>('/api/equipment/types', {
    method: 'POST',
    body: {
      name: `Integration Projector ${uniqueEmail('equipment')}`,
      total_quantity: 10,
      store_name: 'Main store',
    },
  })
  return equipmentType.id
}

/** As the staff account: ask for two units of a new equipment type. Returns the line's id. */
async function addEquipmentRequest(reference: string): Promise<number> {
  const equipmentTypeId = await newEquipmentType()
  await signInAs(staffAccount())
  const line = await addEquipmentLine(reference, {
    equipment_type_id: equipmentTypeId,
    quantity: 2,
  })
  return line.id
}

/** A note on each of the Safety Officer's seven checklist items (SCRUM-98 AC2). */
const SAFETY_CHECKLIST = {
  attendance_vs_capacity: '120 expected in a hall for 300.',
  venue_layout: 'Theatre layout, aisles clear.',
  emergency_access: 'Two exits, both signed.',
  accessibility: 'Step-free entrance confirmed.',
  equipment_placement: 'No equipment requested.',
  crowd_movement: 'One-way flow at the doors.',
  venue_restrictions: 'No open flames.',
}

/** A settled event the staff account sent to safety review, signed in as it. */
async function eventInSafetyReview(): Promise<PlannedEvent> {
  const event = await settledEvent()
  await sendToSafetyReview(event.reference)
  return event
}

/** An event in safety review the Safety Officer approved: ready to confirm, signed in as staff. */
async function safetyApprovedEvent(): Promise<PlannedEvent> {
  const event = await eventInSafetyReview()
  await signInAs(required(SAFETY_OFFICER))
  await apiRequest(`/api/events/requests/${event.reference}/safety-outcome`, {
    method: 'POST',
    body: { outcome: 'approved', checklist: SAFETY_CHECKLIST },
  })
  await signInAs(staffAccount())
  return event
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-97 sending an event to safety review against the backend', () => {
  it('refuses an organiser by role, and a visitor without a token', async () => {
    const { reference } = await submittedEvent()

    expect(await refusal(sendToSafetyReview(reference))).toMatchObject(NOT_PERMITTED)
    sendRequestsAs(null)
    expect(await refusal(sendToSafetyReview(reference))).toMatchObject(NOT_SIGNED_IN)
  })

  it('answers a coordinator an event not assigned to them as not found', async () => {
    const { reference } = await submittedEvent()
    await signInAs(staffAccount())

    expect(await refusal(sendToSafetyReview(reference))).toMatchObject(NOT_FOUND)
  })

  it.skipIf(!canAssign)('refuses an event not yet approved, with no gaps', async () => {
    const { reference } = await assignedEvent()

    const error = await refusal(sendToSafetyReview(reference))

    expect(error).toMatchObject({
      status: 409,
      code: 'safety_review_not_allowed',
      message: 'Only an approved event can go to Safety Review.',
    })
    expect(error.fieldErrors).toEqual({})
  })

  it.skipIf(!canAssign)('names a missing venue on an approved event with none', async () => {
    const { reference } = await approvedEvent()

    const error = await refusal(sendToSafetyReview(reference))

    expect(error).toMatchObject(SAFETY_REVIEW_NOT_READY)
    expect(error.fieldErrors).toEqual({ venue_arrangements: ['The event has no venue arranged.'] })
  })

  it.skipIf(!canApproveVenue)(
    'names a pending venue arrangement by its id and status',
    async () => {
      const { reference } = await approvedEvent()
      const bookingId = await raiseVenueRequest(reference)

      const error = await refusal(sendToSafetyReview(reference))

      expect(error).toMatchObject(SAFETY_REVIEW_NOT_READY)
      expect(error.fieldErrors).toEqual({
        venue_arrangements: [`Venue arrangement ${bookingId} is pending.`],
      })
    },
  )

  it.skipIf(!canApproveVenue)(
    'sends a settled event, answering in the shape the page reads',
    async () => {
      const { reference } = await settledEvent()

      const sent = await sendToSafetyReview(reference)

      expect(Object.keys(sent).sort()).toEqual(EVENT_REQUEST_FIELDS)
      expect(sent).toMatchObject({ reference, status: 'safety_review' })
      expect((await fetchEventRequest(reference)).status).toBe('safety_review')
    },
  )
})

describe('SCRUM-68 marking an event completed against the backend', () => {
  it('refuses an organiser by role, and a visitor without a token', async () => {
    const { reference } = await submittedEvent()

    expect(await refusal(completeEvent(reference))).toMatchObject(NOT_PERMITTED)
    sendRequestsAs(null)
    expect(await refusal(completeEvent(reference))).toMatchObject(NOT_SIGNED_IN)
  })

  it('answers a coordinator an event not assigned to them as not found', async () => {
    const { reference } = await submittedEvent()
    await signInAs(staffAccount())

    expect(await refusal(completeEvent(reference))).toMatchObject(NOT_FOUND)
  })

  it.skipIf(!canAssign)('refuses an event that is not confirmed', async () => {
    const { reference } = await approvedEvent()

    expect(await refusal(completeEvent(reference))).toMatchObject({
      status: 409,
      code: 'request_not_completable',
      message: 'Only a confirmed event can be marked completed.',
    })
  })
})

describe('SCRUM-69 registration settings against the backend', () => {
  it('refuses an organiser by role, and a visitor without a token', async () => {
    const { reference } = await submittedEvent()

    const change = { registration_enabled: false }
    expect(await refusal(updateRegistrationSettings(reference, change))).toMatchObject(
      NOT_PERMITTED,
    )
    sendRequestsAs(null)
    expect(await refusal(updateRegistrationSettings(reference, change))).toMatchObject(
      NOT_SIGNED_IN,
    )
  })

  it('answers a coordinator an event not assigned to them as not found', async () => {
    const { reference } = await submittedEvent()
    await signInAs(staffAccount())

    const error = await refusal(updateRegistrationSettings(reference, { registration_capacity: 5 }))

    expect(error).toMatchObject(NOT_FOUND)
  })

  it.skipIf(!canAssign)(
    'stores a capacity with registration closed, answering in the shape the page reads',
    async () => {
      const { reference } = await approvedEvent()

      const settings = await updateRegistrationSettings(reference, {
        registration_enabled: false,
        registration_capacity: 50,
      })

      expect(settings).toEqual({
        reference,
        registration_required: false,
        registration_enabled: false,
        registration_capacity: 50,
        withdrawal_cut_off: null,
      })
    },
  )

  it.skipIf(!canAssign)(
    'records a withdrawal cut-off before the start in business time, refuses one at the start, and clears it (AC6)',
    async () => {
      const { reference } = await approvedEvent()
      const dayBefore = `${daysFromNow(29)}T18:00:00+08:00`

      const recorded = await updateRegistrationSettings(reference, {
        registration_enabled: false,
        withdrawal_cut_off: `${daysFromNow(29)}T10:00:00Z`,
      })
      const atTheStart = await refusal(
        updateRegistrationSettings(reference, { withdrawal_cut_off: `${EVENT_DATE}T09:00:00` }),
      )
      const cleared = await updateRegistrationSettings(reference, { withdrawal_cut_off: null })

      expect(recorded.withdrawal_cut_off).toBe(dayBefore)
      expect(atTheStart).toMatchObject({ status: 400, code: 'validation_error' })
      expect(atTheStart.fieldErrors).toEqual({
        withdrawal_cut_off: ['The withdrawal cut-off must be before the event starts.'],
      })
      expect(cleared.withdrawal_cut_off).toBeNull()
    },
  )

  it.skipIf(!canAssign)('asks for a capacity under its field to open registration', async () => {
    const { reference } = await approvedEvent()

    const error = await refusal(
      updateRegistrationSettings(reference, { registration_enabled: true }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      registration_capacity: ['A capacity is required to enable registration.'],
    })
  })

  it.skipIf(!canAssign)('names a capacity that is not a whole number from 1 up', async () => {
    const { reference } = await approvedEvent()

    const zero = await refusal(updateRegistrationSettings(reference, { registration_capacity: 0 }))
    const fraction = await refusal(
      updateRegistrationSettings(reference, { registration_capacity: 1.5 }),
    )

    expect(zero.fieldErrors).toEqual({
      registration_capacity: ['Capacity must be between 1 and 2147483647.'],
    })
    expect(fraction.fieldErrors).toEqual({ registration_capacity: ['Not a valid integer.'] })
  })

  it.skipIf(!canAssign)('refuses to open registration before the event is confirmed', async () => {
    const { reference } = await approvedEvent()

    const error = await refusal(
      updateRegistrationSettings(reference, {
        registration_enabled: true,
        registration_capacity: 50,
      }),
    )

    expect(error).toMatchObject({
      status: 409,
      code: 'registration_not_enablable',
      message: 'Registration can be enabled only for a confirmed event.',
    })
  })
})

describe('SCRUM-49 confirming an event against the backend', () => {
  const CONFIRMATION_NOT_READY = {
    status: 409,
    code: 'confirmation_not_allowed',
    message:
      'The event can be confirmed once the Safety Officer has approved it, every venue ' +
      'arrangement is approved and every equipment request has an outcome from Technical ' +
      'Support.',
  }

  it('refuses an organiser by role, and a visitor without a token', async () => {
    const { reference } = await submittedEvent()

    expect(await refusal(confirmEvent(reference))).toMatchObject(NOT_PERMITTED)
    sendRequestsAs(null)
    expect(await refusal(confirmEvent(reference))).toMatchObject(NOT_SIGNED_IN)
  })

  it('answers a coordinator an event not assigned to them as not found', async () => {
    const { reference } = await submittedEvent()
    await signInAs(staffAccount())

    expect(await refusal(confirmEvent(reference))).toMatchObject(NOT_FOUND)
  })

  it.skipIf(!canAssign)('refuses an event not in safety review, with no gaps', async () => {
    const { reference } = await approvedEvent()

    const error = await refusal(confirmEvent(reference))

    expect(error).toMatchObject({
      status: 409,
      code: 'confirmation_not_allowed',
      message: 'Only an event in Safety Review can be confirmed.',
    })
    expect(error.fieldErrors).toEqual({})
  })

  it.skipIf(!canApproveVenue)(
    'names the missing safety approval of a settled event in safety review',
    async () => {
      const { reference } = await eventInSafetyReview()

      const error = await refusal(confirmEvent(reference))

      expect(error).toMatchObject(CONFIRMATION_NOT_READY)
      expect(error.fieldErrors).toEqual({
        safety_check: ['The Safety Officer has not approved the event.'],
      })
    },
  )

  it.skipIf(!canApproveSafety)(
    'confirms once every approval is in, tells the organiser, and then takes registration but not completion',
    async () => {
      const { reference, organiser } = await safetyApprovedEvent()

      const confirmed = await confirmEvent(reference)

      expect(Object.keys(confirmed).sort()).toEqual(EVENT_REQUEST_FIELDS)
      expect(confirmed).toMatchObject({ reference, status: 'confirmed' })
      // --- Registration opens now that the event is confirmed (SCRUM-69 AC4) ---
      const settings = await updateRegistrationSettings(reference, {
        registration_enabled: true,
        registration_capacity: 80,
      })
      expect(settings).toMatchObject({ registration_enabled: true, registration_capacity: 80 })
      // --- The event is a month away, so it can't be completed yet (SCRUM-68 AC2) ---
      expect(await refusal(completeEvent(reference))).toMatchObject({
        status: 409,
        code: 'request_not_completable',
        message: 'The event has not ended yet.',
      })
      // --- The organiser's notice is the backend's own (SCRUM-49 AC12) ---
      await signInAs(organiser)
      const notices = await fetchNotifications()
      const notice = notices.find((notification) => notification.kind === 'event_confirmed')
      expect(notice).toMatchObject({
        event_reference: reference,
        message: 'Your event has been confirmed.',
      })
    },
  )
})

describe('SCRUM-31 AC7 a venue booking request locks the decision against the backend', () => {
  const CHANGE = { outcome: 'rejected', reason: 'The venue fell through.' } as const
  const DECISION_LOCKED = {
    status: 409,
    code: 'decision_locked',
    message:
      "The decision can't be changed once the event has an equipment request or a venue " +
      'booking request.',
  }

  it.skipIf(!canApproveVenue)(
    'refuses a new decision while the venue booking request is pending, and allows it once withdrawn (ADR-0084)',
    async () => {
      const { reference } = await approvedEvent()
      const bookingId = await raiseVenueRequest(reference)

      expect(await refusal(decideEventRequest(reference, CHANGE))).toMatchObject(DECISION_LOCKED)
      expect((await fetchEventRequest(reference)).status).toBe('approved')

      await withdrawArrangement(reference, bookingId)
      await decideEventRequest(reference, CHANGE)
      expect((await fetchEventRequest(reference)).status).toBe('rejected')
    },
  )
})

describe('SCRUM-33 AC8 the statuses an event can be edited in, against the backend', () => {
  /** An edit to the description, which the backend must refuse. */
  function refusedNote(reference: string) {
    return refusal(editEventRequest(reference, { description: 'A late note.' }))
  }

  it.skipIf(!canApproveSafety)(
    'refuses an edit to a Confirmed event, pointing to a change request, and changes nothing',
    async () => {
      const { reference } = await safetyApprovedEvent()
      await confirmEvent(reference)

      expect(await refusedNote(reference)).toMatchObject({
        status: 409,
        code: 'request_not_editable',
        message: 'A confirmed event can only be changed through a change request.',
      })
      expect(await fetchEventRequest(reference)).toMatchObject({
        status: 'confirmed',
        description: null,
      })
    },
  )

  it.skipIf(!canAssign)(
    'refuses an edit to a rejected event with the general message',
    async () => {
      const { reference } = await assignedEvent()
      await startEventRequestReview(reference)
      await decideEventRequest(reference, { outcome: 'rejected', reason: 'It clashes with exams.' })

      expect(await refusedNote(reference)).toMatchObject({
        status: 409,
        code: 'request_not_editable',
        message:
          'An event request can only be edited before it is confirmed, and not once it is ' +
          'rejected or cancelled.',
      })
      expect((await fetchEventRequest(reference)).description).toBeNull()
    },
  )

  it.skipIf(!canAssign)(
    "lets the coordinator record an amendment while the organiser's answer is awaited",
    async () => {
      const { reference } = await assignedEvent()
      await startEventRequestReview(reference)
      await requestClarification(reference, 'Which hall would suit?')

      const edited = await editEventRequest(reference, { description: 'The main hall.' })

      expect(edited).toMatchObject({
        status: 'awaiting_clarification',
        description: 'The main hall.',
      })
    },
  )
})

describe('SCRUM-33 AC7 a significant edit after the safety check, against the backend', () => {
  it.skipIf(!canApproveSafety)(
    'keeps an event in Safety Review for a note, and sends it back to Approved without its approval for a significant change',
    async () => {
      const { reference } = await safetyApprovedEvent()

      const noted = await editEventRequest(reference, { description: 'Doors open at 9.' })
      // Fewer people: significant, but the hall booked for all 120 still holds them, so no
      // arrangement is flagged to hold back the new check (SCRUM-33 AC6, ADR-0094).
      const changed = await editEventRequest(reference, { expected_attendance: 100 })

      expect(noted.status).toBe('safety_review')
      expect(changed.status).toBe('approved')
      // --- A new safety check is needed before it can be confirmed again (ADR-0087) ---
      await sendToSafetyReview(reference)
      const error = await refusal(confirmEvent(reference))
      expect(error.fieldErrors).toEqual({
        safety_check: ['The Safety Officer has not approved the event.'],
      })
    },
  )
})

describe('SCRUM-48 no equipment outcome on a closed event against the backend', () => {
  it.skipIf(!canRecordOutcome)(
    'refuses an outcome once the coordinator has rejected the event, naming its status, and keeps the line as it was (AC8)',
    async () => {
      const { reference } = await assignedEvent()
      const lineId = await addEquipmentRequest(reference)
      await decideEventRequest(reference, { outcome: 'rejected', reason: 'It clashes with exams.' })
      await signInAs(required(TECH_SUPPORT))

      const error = await refusal(
        recordEquipmentOutcome(reference, { lineId, body: { provided_quantity: 2 } }),
      )

      expect(error).toMatchObject({
        status: 409,
        code: 'conflict',
        message:
          "An equipment outcome can't be recorded for an event that is completed, cancelled " +
          'or rejected; this one is rejected.',
      })
      const { equipment_lines: lines } = await fetchEventEquipmentLines(reference)
      expect(lines.find((line) => line.id === lineId)).toMatchObject({
        status: 'requested',
        provided_quantity: null,
      })
    },
  )
})

describe('SCRUM-49 rejecting an event during planning against the backend', () => {
  const REASON = 'No venue large enough is free that week.'

  it('refuses an organiser by role, and a visitor without a token', async () => {
    const { reference } = await submittedEvent()

    expect(await refusal(rejectEvent(reference, { reason: REASON }))).toMatchObject(NOT_PERMITTED)
    sendRequestsAs(null)
    expect(await refusal(rejectEvent(reference, { reason: REASON }))).toMatchObject(NOT_SIGNED_IN)
  })

  it('answers a coordinator an event not assigned to them as not found', async () => {
    const { reference } = await submittedEvent()
    await signInAs(staffAccount())

    expect(await refusal(rejectEvent(reference, { reason: REASON }))).toMatchObject(NOT_FOUND)
  })

  it.skipIf(!canAssign)(
    'refuses a request still awaiting its first decision, before reading the body',
    async () => {
      const { reference } = await assignedEvent()

      expect(await refusal(rejectEvent(reference, {}))).toMatchObject({
        status: 409,
        code: 'rejection_not_allowed',
        message: 'Only an approved event or one in Safety Review can be rejected during planning.',
      })
    },
  )

  it.skipIf(!canAssign)('asks for a reason under its field', async () => {
    const { reference } = await approvedEvent()

    const missing = await refusal(rejectEvent(reference, {}))
    const blank = await refusal(rejectEvent(reference, { reason: '   ' }))

    expect(missing).toMatchObject({ status: 400, code: 'validation_error' })
    expect(missing.fieldErrors).toEqual({ reason: ['A reason is required to reject the event.'] })
    expect(blank.fieldErrors).toEqual({ reason: ['Must not be blank.'] })
    expect((await fetchEventRequest(reference)).status).toBe('approved')
  })

  it.skipIf(!canAssign)(
    'rejects an approved event, answering in the shape the page reads, and tells the organiser why',
    async () => {
      const { reference, organiser } = await approvedEvent()

      const rejected = await rejectEvent(reference, { reason: REASON })

      expect(Object.keys(rejected).sort()).toEqual(EVENT_REQUEST_FIELDS)
      expect(rejected).toMatchObject({ reference, status: 'rejected' })
      await signInAs(organiser)
      const notices = await fetchNotifications()
      const notice = notices.find((notification) => notification.kind === 'event_request_rejected')
      expect(notice).toMatchObject({
        event_reference: reference,
        message: 'Your event request was rejected.',
        detail: REASON,
      })
    },
  )

  it.skipIf(!canApproveVenue)(
    'releases an approved venue and withdraws a pending one (AC10)',
    async () => {
      const { reference } = await settledEvent()
      const [booked] = await fetchBookingRequests(reference)
      const pendingId = await raiseVenueRequest(reference)

      await rejectEvent(reference, { reason: REASON })

      const statuses = (await fetchBookingRequests(reference)).map((arrangement) => [
        arrangement.id,
        arrangement.status,
      ])
      expect(statuses).toEqual(
        expect.arrayContaining([
          [booked?.id, 'released'],
          [pendingId, 'withdrawn'],
        ]),
      )
    },
  )

  it.skipIf(!canApproveVenue)(
    'rejects an event in Safety Review, releasing its venue',
    async () => {
      const { reference } = await eventInSafetyReview()

      const rejected = await rejectEvent(reference, { reason: REASON })

      expect(rejected.status).toBe('rejected')
      const statuses = (await fetchBookingRequests(reference)).map(
        (arrangement) => arrangement.status,
      )
      expect(statuses).toEqual(['released'])
    },
  )
})

describe('SCRUM-33 reassessing the venue arrangement after a significant edit, against the backend', () => {
  it.skipIf(!canApproveVenue)(
    'holds back safety review while a rise in attendance leaves the arrangement to reconfirm',
    async () => {
      const { reference, bookingId } = await settledEvent()

      await editEventRequest(reference, { expected_attendance: 150 })
      const error = await refusal(sendToSafetyReview(reference))

      // --- Only the arrangement booked for everyone is flagged, with why (SCRUM-33 AC6) ---
      expect(error).toMatchObject(SAFETY_REVIEW_NOT_READY)
      expect(error.fieldErrors).toEqual({
        venue_arrangements: [
          `Venue arrangement ${bookingId} is flagged (requires reconfirmation): The event's ` +
            "expected attendance rose from 120 to 150, above this arrangement's expected " +
            'occupancy of 120.',
        ],
      })
    },
  )

  it.skipIf(!canApproveVenue)(
    'takes a replacement at the flagged arrangement’s own venue for a new time (ADR-0100)',
    async () => {
      const { reference, bookingId } = await settledEvent()
      await editEventRequest(reference, { end_time: '18:00' })
      const [original] = await fetchBookingRequests(reference)
      if (original === undefined) {
        throw new Error('The settled event should have its approved venue arrangement.')
      }

      // A replacement clears a change flag (Product Owner 25 Oct), and the different-venue
      // rule is only for a venue that became unavailable (SCRUM-92).
      const replacement = await raiseBookingRequest(reference, {
        venue_id: original.venue_id,
        starts_at: `${EVENT_DATE}T13:00:00+08:00`,
        ends_at: `${EVENT_DATE}T16:00:00+08:00`,
        purpose: 'Integration replacement after a change',
        replaces_request_id: bookingId,
      })

      expect(original.flagged_after_change).toBe(true)
      expect(replacement).toMatchObject({
        status: 'pending',
        venue_id: original.venue_id,
        replaces_request_id: bookingId,
      })
    },
  )
})

describe('SCRUM-92 replacing a venue that became unavailable', () => {
  /** The settled event's one arrangement, as the coordinator's list shows it. */
  async function onlyArrangement(reference: string): Promise<BookingRequest> {
    const [arrangement] = await fetchBookingRequests(reference)
    if (arrangement === undefined) {
      throw new Error('The settled event should have its approved venue arrangement.')
    }
    return arrangement
  }

  /** One of the event's arrangements, as the coordinator's list shows it. */
  async function arrangementOf(reference: string, id: number): Promise<BookingRequest> {
    const listed = await fetchBookingRequests(reference)
    const arrangement = listed.find((each) => each.id === id)
    if (arrangement === undefined) {
      throw new Error(`The event should list its venue arrangement ${String(id)}.`)
    }
    return arrangement
  }

  /**
   * As Venue Staff: block the arrangement's venue for the whole event day, then sign back in.
   * Returns the block.
   */
  async function blockVenueOf(arrangement: BookingRequest): Promise<CreatedBlock> {
    await signInAs(required(VENUE_STAFF))
    const block = await blockVenue(arrangement.venue_id, {
      start_time: `${EVENT_DATE}T08:00`,
      end_time: `${EVENT_DATE}T18:00`,
      category: 'equipment_failure',
      reason: 'Lift broken',
    })
    await signInAs(staffAccount())
    return block
  }

  it.skipIf(!canApproveVenue)(
    'flags the booked arrangement, takes a replacement linked to it, and releases it once the replacement is approved',
    async () => {
      const { reference } = await settledEvent()
      const original = await onlyArrangement(reference)

      await blockVenueOf(original)

      // --- The block flags the booking, with its category, note and period (AC1, AC2) ---
      const flagged = await onlyArrangement(reference)
      expect(flagged).toMatchObject({ status: 'approved', needs_alternative_venue: true })
      expect(flagged.unavailability).toEqual([
        {
          category: 'equipment_failure',
          reason: 'Lift broken',
          starts_at: `${EVENT_DATE}T08:00:00+08:00`,
          ends_at: `${EVENT_DATE}T18:00:00+08:00`,
        },
      ])
      // --- A replacement for the same period names the flagged arrangement (AC6) ---
      const otherVenue = await newVenue()
      await signInAs(staffAccount())
      const replacement = await raiseBookingRequest(reference, {
        venue_id: otherVenue,
        starts_at: original.starts_at,
        ends_at: original.ends_at,
        purpose: 'Integration replacement',
        replaces_request_id: original.id,
      })
      expect(replacement).toMatchObject({ status: 'pending', replaces_request_id: original.id })
      // --- An arrangement with no flag can't be replaced (ADR-0053 decision 10) ---
      const error = await refusal(
        raiseBookingRequest(reference, {
          venue_id: otherVenue,
          starts_at: `${EVENT_DATE}T13:00:00+08:00`,
          ends_at: `${EVENT_DATE}T15:00:00+08:00`,
          purpose: 'Integration second replacement',
          replaces_request_id: replacement.id,
        }),
      )
      expect(error).toMatchObject({ status: 400, code: 'validation_error' })
      expect(error.fieldErrors).toEqual({
        replaces_request_id: ['This venue arrangement does not need an alternative venue.'],
      })
      // --- Approving the replacement releases the original, which keeps why (AC7) ---
      await signInAs(required(VENUE_STAFF))
      await decideBookingRequest(replacement.id, { outcome: 'approved' })
      await signInAs(staffAccount())
      const listed = await fetchBookingRequests(reference)
      expect(listed.map((each) => [each.id, each.status, each.needs_alternative_venue])).toEqual([
        [original.id, 'released', false],
        [replacement.id, 'approved', false],
      ])
      expect(listed[0]?.unavailability).toHaveLength(1)
    },
  )

  it.skipIf(!canApproveVenue)(
    'refuses a replacement at the venue it replaces, on venue_id, whatever the period (AC6)',
    async () => {
      const { reference } = await settledEvent()
      const original = await onlyArrangement(reference)
      await blockVenueOf(original)
      const sameVenue = { venue_id: original.venue_id, replaces_request_id: original.id }

      const samePeriod = await refusal(
        raiseBookingRequest(reference, {
          ...sameVenue,
          starts_at: original.starts_at,
          ends_at: original.ends_at,
          purpose: 'Integration same-venue replacement',
        }),
      )
      const laterPeriod = await refusal(
        raiseBookingRequest(reference, {
          ...sameVenue,
          starts_at: `${EVENT_DATE}T13:00:00+08:00`,
          ends_at: `${EVENT_DATE}T15:00:00+08:00`,
          purpose: 'Integration same-venue replacement, later',
        }),
      )

      const sameVenueRefusal = {
        status: 400,
        code: 'validation_error',
        fieldErrors: {
          venue_id: ['A replacement must be at a different venue from the one it replaces.'],
        },
      }
      expect([samePeriod, laterPeriod]).toMatchObject([sameVenueRefusal, sameVenueRefusal])
      // Nothing was saved: the flagged arrangement is still the event's only one.
      expect(await fetchBookingRequests(reference)).toHaveLength(1)
    },
  )

  it.skipIf(!canApproveVenue)(
    'tells the coordinator why, and clears the flag once Venue Staff remove the block (AC5, AC8)',
    async () => {
      const { reference } = await settledEvent()
      const original = await onlyArrangement(reference)
      const block = await blockVenueOf(original)

      // --- The coordinator is told the venue, the reason and the period (AC5) ---
      const notices = await fetchNotifications()
      const notice = notices.find(
        (notification) =>
          notification.kind === 'alternative_venue_needed' &&
          notification.event_reference === reference,
      )
      // The venue's name (newVenue's "Integration Hall <unique>"), then the period and the reason.
      expect(notice?.detail).toMatch(/^Integration Hall /)
      expect(notice?.detail).toContain(
        `is unavailable from ${EVENT_DATE} 08:00 to ${EVENT_DATE} 18:00 (equipment failure): Lift broken`,
      )
      // --- Removing the block clears the flag; the original booking stands (AC8) ---
      await signInAs(required(VENUE_STAFF))
      await removeVenueBlock(original.venue_id, block.id)
      await signInAs(staffAccount())
      expect(await onlyArrangement(reference)).toMatchObject({
        id: original.id,
        status: 'approved',
        needs_alternative_venue: false,
        unavailability: [],
      })
    },
  )

  it.skipIf(!canApproveVenue)(
    'flags a request On Hold, and releases it and its hold once its replacement is approved (AC1, AC7)',
    async () => {
      const { reference } = await approvedEvent()
      const heldId = await raiseVenueRequest(reference)
      // A second venue makes the event multi-venue, so Venue Staff may hold the first (SCRUM-75).
      await raiseVenueRequest(reference)
      await signInAs(required(VENUE_STAFF))
      await placeBookingHold(heldId, { expires_at: `${EVENT_DATE}T08:00:00+08:00` })
      await signInAs(staffAccount())
      const held = await arrangementOf(reference, heldId)

      await blockVenueOf(held)

      // --- A tentative hold is a booking too, so the block flags it (AC1, ADR-0100) ---
      expect(await arrangementOf(reference, heldId)).toMatchObject({
        status: 'on_hold',
        needs_alternative_venue: true,
      })
      // --- Approving its replacement releases it and its hold (AC7) ---
      const otherVenue = await newVenue()
      await signInAs(staffAccount())
      const replacement = await raiseBookingRequest(reference, {
        venue_id: otherVenue,
        starts_at: held.starts_at,
        ends_at: held.ends_at,
        purpose: 'Integration replacement for a hold',
        replaces_request_id: heldId,
      })
      await signInAs(required(VENUE_STAFF))
      await decideBookingRequest(replacement.id, { outcome: 'approved' })
      const calendar = await fetchVenueCalendar(held.venue_id, {
        range_start: `${EVENT_DATE}T00:00`,
        range_end: `${EVENT_DATE}T23:59`,
      })
      // Only the block is left: the hold no longer holds the venue.
      expect(calendar.map((entry) => entry.kind)).toEqual(['block'])
      await signInAs(staffAccount())
      expect(await arrangementOf(reference, heldId)).toMatchObject({
        status: 'released',
        needs_alternative_venue: false,
        hold_expires_at: null,
      })
    },
  )
})
