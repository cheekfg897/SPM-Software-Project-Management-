import {
  fetchMyRegisteredEvent,
  registerForEvent,
  withdrawFromEvent,
} from '@/features/catalogue/api'
import { updateRegistrationSettings } from '@/features/eventRequests/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'
import { EVENT_DATE, LEAD, registrableEvent, SAFETY_OFFICER, VENUE_STAFF } from './plannedEvent'

/**
 * SCRUM-24 AC11: an Attendee opens an event they registered for, against the real backend
 * (docs/adr/0109). The refusals need no event and run every time. Registering needs an event
 * taken to Confirmed, which needs the Lead, Venue Staff and Safety Officer accounts CI makes, so
 * those checks skip without them.
 */

const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event not found.' }
/** Every field the page reads, as the backend sends them. */
const MY_REGISTERED_EVENT_FIELDS = [
  'can_withdraw',
  'description',
  'ends_at',
  'event_status',
  'id',
  'name',
  'reference',
  'registered_at',
  'starts_at',
  'status',
  'venues',
  'withdrawals_close_at',
  'withdrawn_at',
]
/** A reference no event has. */
const MISSING_REFERENCE = 'EVR-NOTHERE1'
/** A cut-off long past, but before the event starts, as SCRUM-69 AC6 requires. */
const PAST_CUT_OFF = '2026-01-01T09:00:00+08:00'

const canRegister = LEAD !== null && VENUE_STAFF !== null && SAFETY_OFFICER !== null

afterEach(() => sendRequestsAs(null))

describe('SCRUM-24 AC11 an attendee opens an event they registered for, against the backend', () => {
  it('refuses a visitor (401) and another role (403)', async () => {
    const visitor = await refusal(fetchMyRegisteredEvent(MISSING_REFERENCE))
    await signInAs(staffAccount())
    const coordinator = await refusal(fetchMyRegisteredEvent(MISSING_REFERENCE))

    expect(visitor).toMatchObject({ status: 401, code: 'authentication_error' })
    expect(coordinator).toMatchObject({
      status: 403,
      code: 'authorization_error',
      message: 'You do not have permission to perform this action.',
    })
  })

  it('answers 404 for a reference no event has', async () => {
    await signInAsNewAttendee()

    expect(await refusal(fetchMyRegisteredEvent(MISSING_REFERENCE))).toMatchObject(NOT_FOUND)
  })

  it.skipIf(!canRegister)(
    'opens a registered event with its venue, offers Withdraw before it starts, and shows the withdrawal from a fresh session',
    async () => {
      const event = await registrableEvent()
      const attendee = await signInAsNewAttendee()
      await registerForEvent(event.id)

      const opened = await fetchMyRegisteredEvent(event.reference)

      expect(Object.keys(opened).sort()).toEqual(MY_REGISTERED_EVENT_FIELDS)
      expect(opened).toMatchObject({
        id: event.id,
        reference: event.reference,
        name: event.name,
        event_status: 'confirmed',
        status: 'registered',
        withdrawn_at: null,
        withdrawals_close_at: `${EVENT_DATE}T09:00:00+08:00`,
        can_withdraw: true,
      })
      expect(opened.venues).toEqual([
        { name: expect.stringMatching(/^Integration Hall /) as string, location: 'Level 1' },
      ])
      // --- Another attendee, who never registered, can't open it ---
      await signInAsNewAttendee()
      expect(await refusal(fetchMyRegisteredEvent(event.reference))).toMatchObject(NOT_FOUND)
      // --- Withdrawing shows on the page, read again in a new session ---
      await signInAs(attendee)
      await withdrawFromEvent(event.id)
      sendRequestsAs(null)
      await signInAs(attendee)
      expect(await fetchMyRegisteredEvent(event.reference)).toMatchObject({
        status: 'withdrawn',
        withdrawn_at: expect.any(String) as string,
        can_withdraw: false,
      })
    },
  )

  it.skipIf(!canRegister)(
    'offers no Withdraw once the cut-off has passed, and the backend refuses one too',
    async () => {
      const event = await registrableEvent()
      await updateRegistrationSettings(event.reference, { withdrawal_cut_off: PAST_CUT_OFF })
      await signInAsNewAttendee()
      await registerForEvent(event.id)

      const opened = await fetchMyRegisteredEvent(event.reference)
      const refused = await refusal(withdrawFromEvent(event.id))

      expect(opened).toMatchObject({ withdrawals_close_at: PAST_CUT_OFF, can_withdraw: false })
      expect(refused).toMatchObject({
        status: 409,
        code: 'withdrawal_closed',
        message: 'Withdrawals for this event have closed.',
        details: { withdrawal_closed_at: PAST_CUT_OFF },
      })
    },
  )
})
