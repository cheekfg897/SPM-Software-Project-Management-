import { fetchRegistrants } from '@/features/eventRequests/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

/**
 * The mock of an event's registrants (GET /api/events/requests/<reference>/registrations),
 * pinned to what the backend sends (SCRUM-55 AC1 to AC5): who may read them, in which order,
 * and the count against the capacity. The integration tests check the same shape against the
 * running backend.
 */

/** Chloe's confirmed event, in organisation 2, Sara's: three registrants and 80 places. */
const TOWN_HALL = 'EVR-BOOK0102'
/** Chloe's, under review, in the mock organiser's organisation: nobody registered yet. */
const PARTNER_SUMMIT = 'EVR-7K2M9QXA'
const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event request not found.' }
const NOT_PERMITTED = { status: 403, code: 'authorization_error' }

const TOWN_HALL_REGISTRANTS = {
  capacity: 80,
  registered_count: 3,
  places_left: 77,
  items: [
    {
      name: 'Hannah Lee',
      email: 'hannah.lee@example.com',
      registered_at: '2026-10-06T09:15:00+08:00',
      status: 'registered',
    },
    {
      name: 'Ravi Kumar',
      email: 'ravi.kumar@example.com',
      registered_at: '2026-10-07T18:40:00+08:00',
      status: 'registered',
    },
    {
      name: 'Mei Ling Tan',
      email: 'meiling.tan@example.com',
      registered_at: '2026-10-08T12:05:00+08:00',
      status: 'registered',
    },
  ],
}

function signInAs(account: MockAccount | null) {
  sendRequestsAs(account === null ? null : mockTokenFor(account))
}

describe('SCRUM-55 mock of an event registrants: what each viewer sees', () => {
  it('gives the assigned coordinator every registrant, oldest first, against the capacity (AC2, AC3, AC4)', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    expect(await fetchRegistrants(TOWN_HALL)).toEqual(TOWN_HALL_REGISTRANTS)
  })

  it("gives an organiser of the event's organisation the same list (AC1)", async () => {
    signInAs(MOCK_ACCOUNTS.otherOrganiser)

    expect(await fetchRegistrants(TOWN_HALL)).toEqual(TOWN_HALL_REGISTRANTS)
  })

  it('gives an event with no capacity and nobody registered an empty list and nulls', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    expect(await fetchRegistrants(PARTNER_SUMMIT)).toEqual({
      capacity: null,
      registered_count: 0,
      places_left: null,
      items: [],
    })
  })
})

describe('SCRUM-55 mock of an event registrants: who is refused', () => {
  it("answers another organisation's organiser as not found (AC1)", async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    expect(await refusal(fetchRegistrants(TOWN_HALL))).toMatchObject(NOT_FOUND)
  })

  it('answers a coordinator the event is not assigned to as not found (AC2)', async () => {
    signInAs(MOCK_ACCOUNTS.reviewingCoordinator)

    expect(await refusal(fetchRegistrants(TOWN_HALL))).toMatchObject(NOT_FOUND)
  })

  it.each([
    ['an attendee (AC5)', MOCK_ACCOUNTS.attendee],
    ['the Lead', MOCK_ACCOUNTS.lead],
    ['Technical Support', MOCK_ACCOUNTS.technicalSupport],
  ])('refuses %s by role', async (_, account) => {
    signInAs(account)

    expect(await refusal(fetchRegistrants(TOWN_HALL))).toMatchObject(NOT_PERMITTED)
  })

  it('refuses an organiser with no organisation, and a visitor', async () => {
    signInAs(MOCK_ACCOUNTS.unlinkedOrganiser)
    const unlinked = await refusal(fetchRegistrants(PARTNER_SUMMIT))
    signInAs(null)
    const visitor = await refusal(fetchRegistrants(PARTNER_SUMMIT))

    expect(unlinked).toMatchObject({ status: 403, code: 'organiser_without_organisation' })
    expect(visitor).toMatchObject({ status: 401, code: 'authentication_error' })
  })
})
