import { ROLE } from '@/config/roles'
import {
  fetchCatalogue,
  fetchMyEvents,
  registerForEvent,
  withdrawFromEvent,
} from '@/features/catalogue/api'
import { MY_EVENTS_WHEN } from '@/features/catalogue/constants'
import { refusalOf } from '@/test/refusalOf'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'

import { MOCK_ATTENDEE_UNLISTED_EVENTS, MOCK_CATALOGUE_EVENTS } from './catalogueFixtures'
import { accountsOfEveryRoleBut, signInAs } from './test/eventRequestCalls'

/**
 * The catalogue mock's withdrawals (SCRUM-53, docs/adr/0032 *Withdrawing*), pinned to what
 * backend/app/modules/registration answers. The mock's "now" is Monday 5 Oct 2026, 12:00. The
 * mock attendee holds Startup Pitch Night (7 Oct), this morning's Sunrise Yoga, which has
 * started, and the Harbour Lights Run (10 Oct), since cancelled.
 */

function eventNamed(name: string) {
  const event = MOCK_CATALOGUE_EVENTS.find((candidate) => candidate.name === name)
  if (event === undefined) {
    throw new Error(`No catalogue event is called ${name}`)
  }
  return event
}

const PITCH_NIGHT = eventNamed('Startup Pitch Night')
const SUNRISE_YOGA = eventNamed('Sunrise Yoga on the Lawn')
const DATA_VIZ = eventNamed('Data Viz Meetup')
const HARBOUR_RUN = MOCK_ATTENDEE_UNLISTED_EVENTS.find(
  (event) => event.name === 'Harbour Lights Run',
)

/** The catalogue's entry for an event, as the signed-in caller sees it. */
async function listed(eventId: number) {
  const page = await fetchCatalogue({})
  return page.items.find((item) => item.id === eventId)
}

/** The signed-in Attendee's upcoming row for an event, if they have one. */
async function myUpcoming(eventId: number) {
  const list = await fetchMyEvents(MY_EVENTS_WHEN.UPCOMING)
  return list.registrations.find((row) => row.event_id === eventId)
}

beforeEach(() => signInAs(MOCK_ACCOUNTS.attendee))

describe('SCRUM-53 catalogue mock: withdrawing', () => {
  it('answers with the registration, now withdrawn at the mock now', async () => {
    const withdrawn = await withdrawFromEvent(PITCH_NIGHT.id)

    expect(withdrawn).toEqual({
      id: expect.any(Number) as number,
      event_id: PITCH_NIGHT.id,
      status: 'withdrawn',
      registered_at: '2026-10-05T12:00:00+08:00',
      withdrawn_at: '2026-10-05T12:00:00+08:00',
    })
  })

  it('gives the place back to the event, and keeps the registration listed as withdrawn', async () => {
    const before = await listed(PITCH_NIGHT.id)

    await withdrawFromEvent(PITCH_NIGHT.id)

    expect(await listed(PITCH_NIGHT.id)).toMatchObject({
      places_left: (before?.places_left ?? 0) + 1,
      is_registered: false,
    })
    expect(await myUpcoming(PITCH_NIGHT.id)).toMatchObject({
      status: 'withdrawn',
      withdrawn_at: '2026-10-05T12:00:00+08:00',
    })
  })

  it('withdraws from an event the catalogue no longer lists, such as a cancelled one', async () => {
    const eventId = HARBOUR_RUN?.id ?? 0

    await withdrawFromEvent(eventId)

    expect(await myUpcoming(eventId)).toMatchObject({ status: 'withdrawn' })
  })

  it('lets the attendee register again, reusing the registration', async () => {
    const withdrawn = await withdrawFromEvent(PITCH_NIGHT.id)

    const again = await registerForEvent(PITCH_NIGHT.id)

    expect(again).toMatchObject({ id: withdrawn.id, status: 'registered', withdrawn_at: null })
    expect(await myUpcoming(PITCH_NIGHT.id)).toMatchObject({ status: 'registered' })
  })

  it('refuses a second withdrawal (409 already_withdrawn)', async () => {
    await withdrawFromEvent(PITCH_NIGHT.id)

    expect(await refusalOf(withdrawFromEvent(PITCH_NIGHT.id))).toMatchObject({
      status: 409,
      code: 'already_withdrawn',
      message: 'You have already withdrawn from this event.',
    })
  })

  it('refuses once the event has started, giving when withdrawals closed (409 withdrawal_closed)', async () => {
    const error = await refusalOf(withdrawFromEvent(SUNRISE_YOGA.id))

    expect(error).toMatchObject({
      status: 409,
      code: 'withdrawal_closed',
      message: 'Withdrawals for this event have closed.',
      details: { withdrawal_closed_at: SUNRISE_YOGA.starts_at },
    })
  })

  it.each([
    ['an event they never registered for', DATA_VIZ.id],
    ['an event that does not exist', 99_999],
  ])('answers 404 for %s', async (_case, eventId) => {
    expect(await refusalOf(withdrawFromEvent(eventId))).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Registration not found.',
    })
  })
})

describe('SCRUM-53 catalogue mock: who may withdraw', () => {
  it('refuses a visitor (401)', async () => {
    signInAs(null)

    expect(await refusalOf(withdrawFromEvent(PITCH_NIGHT.id))).toMatchObject({
      status: 401,
      code: 'authentication_error',
    })
  })

  it.each(accountsOfEveryRoleBut(ROLE.ATTENDEE))(
    'refuses the %s role (403)',
    async (_role, account) => {
      signInAs(account)

      expect(await refusalOf(withdrawFromEvent(PITCH_NIGHT.id))).toMatchObject({
        status: 403,
        code: 'authorization_error',
      })
    },
  )
})
