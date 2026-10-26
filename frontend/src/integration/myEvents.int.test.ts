import { fetchMyEvents, registerForEvent, withdrawFromEvent } from '@/features/catalogue/api'
import { MY_EVENTS_WHEN } from '@/features/catalogue/constants'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'
import { LEAD, registrableEvent, SAFETY_OFFICER, VENUE_STAFF } from './plannedEvent'

/**
 * SCRUM-24 AC7 and SCRUM-52 AC5: an Attendee's own events against the real backend
 * (docs/adr/0044-attendee-events-list.md).
 *
 * A new attendee holds no places, so most of these check what the backend answers with nothing
 * to list: the empty halves and their messages, and every refusal. Listing a registration needs
 * an event taken to Confirmed (plannedEvent.ts), which needs the Lead, Venue Staff and Safety
 * Officer accounts CI makes, so that check skips without them. An event that has ended or was
 * cancelled can't be made on demand, so those checks wait as todos; the mock handlers stand in.
 */

const MY_EVENTS_PATH = '/api/events/registrations'
const NOT_PERMITTED_MESSAGE = 'You do not have permission to perform this action.'
/** Every field a row of MyEvent reads, as the backend sends them. */
const MY_EVENT_FIELDS = [
  'ends_at',
  'event_id',
  'event_status',
  'name',
  'reference',
  'registered_at',
  'starts_at',
  'status',
  'withdrawn_at',
]
/** Registering needs an event taken to Confirmed, which needs these accounts (plannedEvent.ts). */
const canRegister = LEAD !== null && VENUE_STAFF !== null && SAFETY_OFFICER !== null

afterEach(() => sendRequestsAs(null))

describe('SCRUM-24 my events contract (ADR-0044)', () => {
  it.each([
    [MY_EVENTS_WHEN.UPCOMING, 'You have no upcoming events.'],
    [MY_EVENTS_WHEN.PAST, 'You have no past events.'],
  ])("answers a new attendee's %s with no events and says so", async (when, message) => {
    await signInAsNewAttendee()

    await expect(fetchMyEvents(when)).resolves.toEqual({ registrations: [], message })
  })

  it('answers upcoming when no window is asked for', async () => {
    await signInAsNewAttendee()

    await expect(apiRequest(MY_EVENTS_PATH)).resolves.toEqual({
      registrations: [],
      message: 'You have no upcoming events.',
    })
  })

  it('refuses a window it does not know, and a parameter it does not read', async () => {
    await signInAsNewAttendee()

    const unknownWindow = await refusal(fetchMyEvents('today'))
    const unknownParameter = await refusal(apiRequest(MY_EVENTS_PATH, { query: { colour: 'red' } }))

    expect(unknownWindow).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { when: ['Must be one of: upcoming, past.'] },
    })
    expect(unknownParameter).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { colour: ['Unknown field.'] },
    })
  })

  it('refuses a visitor (401) and another role (403)', async () => {
    const visitor = await refusal(fetchMyEvents(MY_EVENTS_WHEN.UPCOMING))
    await signInAs(staffAccount())
    const coordinator = await refusal(fetchMyEvents(MY_EVENTS_WHEN.UPCOMING))

    expect(visitor).toMatchObject({ status: 401, code: 'authentication_error' })
    expect(coordinator).toMatchObject({
      status: 403,
      code: 'authorization_error',
      message: NOT_PERMITTED_MESSAGE,
    })
  })

  it.skipIf(!canRegister)(
    'lists a registered event under upcoming with every field MyEvent reads, its reference included',
    async () => {
      const event = await registrableEvent()
      await signInAsNewAttendee()
      await registerForEvent(event.id)

      const { registrations } = await fetchMyEvents(MY_EVENTS_WHEN.UPCOMING)

      expect(registrations).toHaveLength(1)
      expect(Object.keys(registrations[0] ?? {}).sort()).toEqual(MY_EVENT_FIELDS)
      expect(registrations[0]).toMatchObject({
        event_id: event.id,
        reference: event.reference,
        name: event.name,
        event_status: 'confirmed',
        status: 'registered',
      })
    },
  )

  it.skipIf(!canRegister)(
    'keeps a withdrawn registration listed, with the event’s status and its own (AC7, 26 Oct)',
    async () => {
      const event = await registrableEvent()
      await signInAsNewAttendee()
      await registerForEvent(event.id)
      await withdrawFromEvent(event.id)

      const { registrations } = await fetchMyEvents(MY_EVENTS_WHEN.UPCOMING)

      expect(registrations).toHaveLength(1)
      expect(registrations[0]).toMatchObject({
        reference: event.reference,
        event_status: 'confirmed',
        status: 'withdrawn',
        withdrawn_at: expect.any(String) as string,
      })
    },
  )

  // These need an event to end or be cancelled, which no route can do on demand.
  it.todo('moves an event that has ended to past, most recent first')
  it.todo('keeps a cancelled event listed with event_status cancelled')
})
