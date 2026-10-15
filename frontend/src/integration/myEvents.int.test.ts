import { fetchMyEvents } from '@/features/catalogue/api'
import { MY_EVENTS_WHEN } from '@/features/catalogue/constants'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'

/**
 * SCRUM-24 AC7 and SCRUM-52 AC5: an Attendee's own events against the real backend
 * (docs/adr/0044-attendee-events-list.md).
 *
 * A new attendee holds no places, and nothing in the API can confirm an event for them to
 * register for yet (SCRUM-49). So these check what the backend answers with nothing to list:
 * the empty halves and their messages, and every refusal. The checks that need a registration
 * wait below as todos, and become real tests once an event can be confirmed. The mock handlers
 * stand in for them until then.
 */

const MY_EVENTS_PATH = '/api/events/registrations'
const NOT_PERMITTED_MESSAGE = 'You do not have permission to perform this action.'

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

  // These need an event the attendee can register for, which nothing can confirm yet (SCRUM-49).
  it.todo('lists a registered event under upcoming with every field MyEvent reads')
  it.todo('moves an event that has ended to past, most recent first')
  it.todo('keeps a cancelled event listed with event_status cancelled')
})
