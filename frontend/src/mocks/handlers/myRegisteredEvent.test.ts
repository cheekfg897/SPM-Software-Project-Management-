import { ROLE } from '@/config/roles'
import {
  fetchMyRegisteredEvent,
  registerForEvent,
  withdrawFromEvent,
} from '@/features/catalogue/api'
import { refusalOf } from '@/test/refusalOf'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'

import { MOCK_CATALOGUE_EVENTS } from './catalogueFixtures'
import { accountsOfEveryRoleBut, signInAs } from './test/eventRequestCalls'

/**
 * The mock of one event an Attendee registered for (SCRUM-24 AC11, docs/adr/0109), pinned to
 * what backend/app/modules/registration answers. The mock's "now" is Monday 5 Oct 2026, 12:00.
 * The mock attendee holds Startup Pitch Night (7 Oct, no cut-off) and this morning's Sunrise Yoga,
 * and registered for the Orchid Show Opening Night, since completed, and the Harbour Lights Run
 * (10 Oct), since cancelled. Data Viz Meetup's cut-off passed at 9 this morning.
 */

const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event not found.' }

function referenceOf(name: string): string {
  const event = MOCK_CATALOGUE_EVENTS.find((candidate) => candidate.name === name)
  if (event === undefined) {
    throw new Error(`No catalogue event is called ${name}`)
  }
  return event.reference
}

function idOf(reference: string): number {
  return MOCK_CATALOGUE_EVENTS.find((event) => event.reference === reference)?.id ?? 0
}

const PITCH_NIGHT = referenceOf('Startup Pitch Night')
const DATA_VIZ = referenceOf('Data Viz Meetup')
const ORCHID_SHOW = 'EVR-MOCK0901'
const HARBOUR_RUN = 'EVR-MOCK0902'

beforeEach(() => signInAs(MOCK_ACCOUNTS.attendee))

describe('SCRUM-24 my registered event mock: what it answers', () => {
  it('answers the public facts, the venues, the registration and the withdrawal', async () => {
    expect(await fetchMyRegisteredEvent(PITCH_NIGHT)).toEqual({
      id: idOf(PITCH_NIGHT),
      reference: PITCH_NIGHT,
      name: 'Startup Pitch Night',
      description: 'Ten founders, five minutes each, one very honest panel.',
      starts_at: '2026-10-07T19:00:00+08:00',
      ends_at: '2026-10-07T21:30:00+08:00',
      event_status: 'confirmed',
      venues: [{ name: 'The Projector, Golden Mile Tower', location: '100 Beach Road, Level 5' }],
      status: 'registered',
      registered_at: '2026-10-05T12:00:00+08:00',
      withdrawn_at: null,
      withdrawals_close_at: '2026-10-07T19:00:00+08:00',
      can_withdraw: true,
    })
  })

  it('reads the reference in any case, with spaces around it', async () => {
    const event = await fetchMyRegisteredEvent(` ${PITCH_NIGHT.toLowerCase()} `)

    expect(event.reference).toBe(PITCH_NIGHT)
  })

  it.each([
    ['completed', ORCHID_SHOW],
    ['cancelled', HARBOUR_RUN],
  ])('opens a %s event read-only, with its status', async (status, reference) => {
    const event = await fetchMyRegisteredEvent(reference)

    expect(event).toMatchObject({ event_status: status, status: 'registered', can_withdraw: false })
  })

  it('keeps the venue of a completed event, and has none for a cancelled one', async () => {
    const completed = await fetchMyRegisteredEvent(ORCHID_SHOW)
    const cancelled = await fetchMyRegisteredEvent(HARBOUR_RUN)

    expect(completed.venues).toEqual([
      { name: 'Gardens by the Bay, Flower Dome', location: '18 Marina Gardens Drive' },
    ])
    expect(cancelled.venues).toEqual([])
  })

  it('offers no Withdraw once the cut-off has passed, and says when it was', async () => {
    await registerForEvent(idOf(DATA_VIZ))

    expect(await fetchMyRegisteredEvent(DATA_VIZ)).toMatchObject({
      withdrawals_close_at: '2026-10-05T09:00:00+08:00',
      can_withdraw: false,
    })
  })

  it('shows a withdrawal made on My events, and offers no Withdraw after it', async () => {
    await withdrawFromEvent(idOf(PITCH_NIGHT))

    expect(await fetchMyRegisteredEvent(PITCH_NIGHT)).toMatchObject({
      status: 'withdrawn',
      withdrawn_at: '2026-10-05T12:00:00+08:00',
      can_withdraw: false,
    })
  })
})

describe('SCRUM-24 my registered event mock: who may open it', () => {
  it('answers 404 to an attendee who never registered, though another attendee did', async () => {
    signInAs(MOCK_ACCOUNTS.freshAttendee)

    expect(await refusalOf(fetchMyRegisteredEvent(PITCH_NIGHT))).toMatchObject(NOT_FOUND)
  })

  it('answers 404 in the same words for a reference no event has', async () => {
    expect(await refusalOf(fetchMyRegisteredEvent('EVR-NOTHERE1'))).toMatchObject(NOT_FOUND)
  })

  it('refuses a visitor (401)', async () => {
    signInAs(null)

    expect(await refusalOf(fetchMyRegisteredEvent(PITCH_NIGHT))).toMatchObject({
      status: 401,
      code: 'authentication_error',
    })
  })

  it.each(accountsOfEveryRoleBut(ROLE.ATTENDEE))(
    'refuses the %s role (403)',
    async (_role, account) => {
      signInAs(account)

      expect(await refusalOf(fetchMyRegisteredEvent(PITCH_NIGHT))).toMatchObject({
        status: 403,
        code: 'authorization_error',
        message: 'You do not have permission to perform this action.',
      })
    },
  )
})
