import { ROLE } from '@/config/roles'
import { register } from '@/features/auth/api'
import {
  decideBookingRequest,
  raiseBookingRequest,
  withdrawArrangement,
} from '@/features/booking/api'
import {
  completeEvent,
  confirmEvent,
  decideEventRequest,
  fetchEventRequest,
  sendToSafetyReview,
  startEventRequestReview,
  submitEventRequest,
  updateRegistrationSettings,
} from '@/features/eventRequests/api'
import { assignCoordinator } from '@/features/lead/api'
import { fetchNotifications } from '@/features/notifications/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, staffAccount, uniqueEmail, VALID_PASSWORD } from './backend'
import type { Credentials } from './backend'

/**
 * The coordinator's planning actions against the running backend: sending an event to safety
 * review (SCRUM-97, ADR-0047), confirming it (SCRUM-49, ADR-0051), its registration settings
 * (SCRUM-69, ADR-0043) and marking it completed (SCRUM-68, ADR-0027) (ADR-0075). Also the
 * decision a venue booking request locks (SCRUM-31 AC7, ADR-0084).
 *
 * The refusals that need no event of the coordinator's run with the staff account every run has
 * (an Event Coordinator) and new organisers. An event of the coordinator's needs a Lead to assign
 * it, an approved venue needs Venue Staff and a safety approval needs a Safety Officer, so those
 * checks read the accounts from INTEGRATION_LEAD_*, INTEGRATION_VENUE_STAFF_* and
 * INTEGRATION_SAFETY_OFFICER_* and skip without them. CI makes all three (frontend.yml).
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
const canAssign = LEAD !== null
const canApproveVenue = canAssign && VENUE_STAFF !== null
const canApproveSafety = canApproveVenue && SAFETY_OFFICER !== null

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

/** An approved event whose one venue Venue Staff approved: ready for safety review. */
async function settledEvent(): Promise<PlannedEvent> {
  const event = await approvedEvent()
  const bookingId = await raiseVenueRequest(event.reference)
  await signInAs(required(VENUE_STAFF))
  await decideBookingRequest(bookingId, { outcome: 'approved' })
  await signInAs(staffAccount())
  return event
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
      })
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
