import { fetchMyEvents } from '@/features/catalogue/api'
import type { MyEventList } from '@/features/catalogue/api'
import { MY_EVENTS_WHEN } from '@/features/catalogue/constants'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'

/**
 * The mock of an Attendee's own events, pinned to docs/adr/0044-attendee-events-list.md.
 * The fixture's "now" is Monday 2026-10-05 12:00 in Singapore. The mock attendee holds a
 * place at Startup Pitch Night (7 Oct) and at this morning's Sunrise Yoga, which has
 * ended, and registered earlier for an event that has taken place, one since called off
 * and one a change sent back to planning (Approved, 14 Oct). Every one is listed, whatever
 * its status (SCRUM-24 AC7, docs/adr/0109). The fresh attendee holds none.
 */

const MY_REGISTRATIONS = '/api/events/registrations'
const CATALOGUE = '/api/events/catalogue'

function namesAndStatuses(list: MyEventList): [string, string][] {
  return list.registrations.map((row) => [row.name, row.event_status])
}

describe('SCRUM-24 my events mock: upcoming and past', () => {
  beforeEach(() => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.attendee))
  })

  it('lists the events that have not ended, soonest first, each with its status', async () => {
    const list = await fetchMyEvents(MY_EVENTS_WHEN.UPCOMING)

    expect(namesAndStatuses(list)).toEqual([
      ['Startup Pitch Night', 'confirmed'],
      ['Harbour Lights Run', 'cancelled'],
      ['Rooftop Film Night', 'approved'],
    ])
    expect(list).not.toHaveProperty('message')
  })

  it('lists the events that have ended, most recent first', async () => {
    const list = await fetchMyEvents(MY_EVENTS_WHEN.PAST)

    expect(namesAndStatuses(list)).toEqual([
      ['Sunrise Yoga on the Lawn', 'confirmed'],
      ['Orchid Show Opening Night', 'completed'],
    ])
  })

  it('answers upcoming when no window is asked for, as the backend does', async () => {
    const list = await apiRequest<MyEventList>(MY_REGISTRATIONS)

    expect(list.registrations.map((row) => row.name)).toEqual([
      'Startup Pitch Night',
      'Harbour Lights Run',
      'Rooftop Film Night',
    ])
  })

  it('gives each row the fields the backend sends', async () => {
    const list = await fetchMyEvents(MY_EVENTS_WHEN.UPCOMING)

    expect(list.registrations[0]).toEqual({
      event_id: expect.any(Number) as number,
      reference: 'EVR-MOCK0005',
      name: 'Startup Pitch Night',
      starts_at: '2026-10-07T19:00:00+08:00',
      ends_at: '2026-10-07T21:30:00+08:00',
      event_status: 'confirmed',
      status: 'registered',
      registered_at: '2026-10-05T12:00:00+08:00',
      withdrawn_at: null,
    })
  })

  it('shows an event the attendee has just registered for', async () => {
    const page = await apiRequest<{
      items: { id: number; name: string; is_registered: boolean }[]
    }>(CATALOGUE)
    const open = page.items.find((item) => !item.is_registered)
    await apiRequest(`${CATALOGUE}/${open?.id ?? 0}/registrations`, { method: 'POST' })

    const list = await fetchMyEvents(MY_EVENTS_WHEN.UPCOMING)

    expect(list.registrations.map((row) => row.name)).toContain(open?.name)
  })
})

describe('SCRUM-24 my events mock: an attendee with none is told so', () => {
  it.each([
    [MY_EVENTS_WHEN.UPCOMING, 'You have no upcoming events.'],
    [MY_EVENTS_WHEN.PAST, 'You have no past events.'],
  ])('%s says "%s"', async (when, message) => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.freshAttendee))

    await expect(fetchMyEvents(when)).resolves.toEqual({ registrations: [], message })
  })
})

describe('SCRUM-24 my events mock: refusals worded as the backend words them', () => {
  it('refuses a visitor who is not signed in', async () => {
    await expect(fetchMyEvents(MY_EVENTS_WHEN.UPCOMING)).rejects.toMatchObject({
      status: 401,
      code: 'authentication_error',
    })
  })

  it('refuses anyone who is not an attendee', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.organiser))

    await expect(fetchMyEvents(MY_EVENTS_WHEN.UPCOMING)).rejects.toMatchObject({
      status: 403,
      code: 'authorization_error',
    })
  })

  it.each([
    [{ when: 'today' }, { when: ['Must be one of: upcoming, past.'] }],
    [{ colour: 'red' }, { colour: ['Unknown field.'] }],
  ])('refuses %j with %j', async (query, fieldErrors) => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.attendee))

    const error = await apiRequest(MY_REGISTRATIONS, { query }).catch((caught: unknown) => caught)

    expect(error).toMatchObject({ status: 400, code: 'validation_error', fieldErrors })
  })
})
