import {
  decideBookingRequest,
  fetchBookingRequests,
  raiseBookingRequest,
} from '@/features/booking/api'
import {
  fetchEventReservations,
  recordEquipmentOutcome,
  reserveEquipment,
} from '@/features/equipment/api'
import { cancelEvent, fetchEventHistory } from '@/features/eventRequests/api'
import { ROLE } from '@/config/roles'
import { apiRequest } from '@/lib/api'
import { refusal } from '@/test/refusal'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'

import { MOCK_BOOKING_VENUES } from './bookingFixtures'
import { MOCK_NOW } from './catalogueFixtures'
import { MOCK_OPEN_EVENT_REFERENCE } from './equipmentFixtures'
import {
  accountsOfEveryRoleBut,
  expectInvalid,
  expectNotAnObject,
  NOT_FOUND,
  NOT_PERMITTED,
  NOT_SIGNED_IN,
  signInAs,
  statusOf,
} from './test/eventRequestCalls'

/**
 * The mock of an Event Organiser cancelling their event (SCRUM-61, ADR-0122), pinned to what
 * the backend does: any organiser of the event's organisation, from submitted to confirmed, with
 * a reason; the event's venues released and its equipment returned, as a rejection during
 * planning does; its check order, codes and messages. The integration test checks the same
 * contract against the backend.
 *
 * Omar (organisation 1) has EVR-Q4ZT6N1B submitted, EVR-7K2M9QXA under review, EVR-B6YF2K8V
 * awaiting clarification, EVR-W9CR5E7M approved, EVR-M1XJ7T3D rejected and his own draft
 * EVR-3HD8PL2W. Sara (organisation 2) sees Hana's events: EVR-PLAN0001 approved (arrangement 41
 * approved, 40 withdrawn, 42 pending), EVR-PLAN0003 in Safety Review, EVR-PLAN0005 confirmed,
 * EVR-PLAN0007 completed and EVR-PLAN0008 cancelled; and Chloe's EVR-BOOK0101 and EVR-MOCK0001.
 */

const OMAR = MOCK_ACCOUNTS.organiser
const SARA = MOCK_ACCOUNTS.otherOrganiser
const CHLOE = MOCK_ACCOUNTS.coordinator
const REASON = 'Our keynote speaker has withdrawn.'
const REASON_REQUIRED = 'A reason is required to cancel the event.'
const APPROVED_WITH_ARRANGEMENTS = 'EVR-PLAN0001'

/** An event in each status the organiser may cancel from, and who may see it. */
const CANCELLABLE = [
  ['submitted', 'EVR-Q4ZT6N1B', OMAR],
  ['under_review', 'EVR-7K2M9QXA', OMAR],
  ['awaiting_clarification', 'EVR-B6YF2K8V', OMAR],
  ['approved', 'EVR-W9CR5E7M', OMAR],
  ['safety_review', 'EVR-PLAN0003', SARA],
  ['confirmed', 'EVR-PLAN0005', SARA],
] as const

/** An event in each other status, and who may see it: each is refused, naming the status. */
const NOT_CANCELLABLE = [
  ['draft', 'EVR-3HD8PL2W', OMAR],
  ['completed', 'EVR-PLAN0007', SARA],
  ['cancelled', 'EVR-PLAN0008', SARA],
  ['rejected', 'EVR-M1XJ7T3D', OMAR],
] as const

function cancelPath(reference: string) {
  return `/api/events/requests/${reference}/cancel`
}

describe('SCRUM-61 mock: an organiser cancels their event', () => {
  it.each(CANCELLABLE)(
    'cancels an event that is %s, in the reply and the record',
    async (_status, reference, account) => {
      signInAs(account)

      const cancelled = await cancelEvent(reference, { reason: `  ${REASON}  ` })

      expect(cancelled).toMatchObject({ reference, status: 'cancelled' })
      expect(await statusOf(reference)).toBe('cancelled')
    },
  )

  it('records the cancellation by the organiser, then withdraws each arrangement not yet approved', async () => {
    signInAs(SARA)

    await cancelEvent(APPROVED_WITH_ARRANGEMENTS, { reason: REASON })

    const byOrganiser = { occurred_at: MOCK_NOW, actor_name: SARA.full_name }
    expect((await fetchEventHistory(APPROVED_WITH_ARRANGEMENTS)).history).toEqual([
      { ...byOrganiser, kind: 'event_cancelled', details: { reason: REASON } },
      {
        ...byOrganiser,
        kind: 'venue_arrangement_withdrawn',
        details: { venue_booking_request_id: 42, venue_id: 3 },
      },
    ])
  })

  it.each([
    [{}, REASON_REQUIRED],
    [{ reason: null }, REASON_REQUIRED],
    [{ reason: '   ' }, 'Must not be blank.'],
    [{ reason: 7 }, 'Not a valid string.'],
  ])('refuses the body %j on reason, and leaves the event as it was', async (body, message) => {
    signInAs(SARA)

    const error = await refusal(
      apiRequest(cancelPath(APPROVED_WITH_ARRANGEMENTS), { method: 'POST', body }),
    )

    expectInvalid(error, { reason: [message] })
    expect(await statusOf(APPROVED_WITH_ARRANGEMENTS)).toBe('approved')
    expect((await fetchEventHistory(APPROVED_WITH_ARRANGEMENTS)).history).toEqual([])
  })

  it('names a field it does not know beside the reason', async () => {
    signInAs(SARA)

    const error = await refusal(
      apiRequest(cancelPath(APPROVED_WITH_ARRANGEMENTS), {
        method: 'POST',
        body: { reason: REASON, status: 'cancelled' },
      }),
    )

    expectInvalid(error, { status: ['Unknown field.'] })
  })

  it('refuses a body that is not a JSON object', async () => {
    signInAs(SARA)

    const error = await refusal(
      apiRequest(cancelPath(APPROVED_WITH_ARRANGEMENTS), { method: 'POST', body: [] }),
    )

    expectNotAnObject(error)
  })

  it.each(NOT_CANCELLABLE)(
    'refuses an event that is %s, before reading the body, naming the status',
    async (status, reference, account) => {
      signInAs(account)

      const error = await refusal(apiRequest(cancelPath(reference), { method: 'POST', body: {} }))

      expect(error).toMatchObject({
        status: 409,
        code: 'cancellation_not_allowed',
        message: `Only an event between Submitted and Confirmed can be cancelled; this one is ${status}.`,
      })
      expect(await statusOf(reference)).toBe(status)
    },
  )

  it("answers another organisation's event as not found, and refuses the unlinked and the signed out", async () => {
    signInAs(OMAR)
    expect(
      await refusal(cancelEvent(APPROVED_WITH_ARRANGEMENTS, { reason: REASON })),
    ).toMatchObject(NOT_FOUND)

    signInAs(MOCK_ACCOUNTS.unlinkedOrganiser)
    expect(
      await refusal(cancelEvent(APPROVED_WITH_ARRANGEMENTS, { reason: REASON })),
    ).toMatchObject({
      status: 403,
      code: 'organiser_without_organisation',
    })

    signInAs(null)
    expect(
      await refusal(cancelEvent(APPROVED_WITH_ARRANGEMENTS, { reason: REASON })),
    ).toMatchObject(NOT_SIGNED_IN)
    signInAs(SARA)
    expect(await statusOf(APPROVED_WITH_ARRANGEMENTS)).toBe('approved')
  })

  it.each(accountsOfEveryRoleBut(ROLE.EVENT_ORGANISER))(
    'refuses %s by role',
    async (_role, account) => {
      signInAs(account)

      expect(
        await refusal(cancelEvent(APPROVED_WITH_ARRANGEMENTS, { reason: REASON })),
      ).toMatchObject(NOT_PERMITTED)
    },
  )
})

/**
 * SCRUM-61 AC2, AC3, AC7: what a cancellation frees lives in the venue and equipment mocks' own
 * stores, so it reaches them as a rejection does, and the event's open equipment requests close
 * with its status. Chloe's EVR-BOOK0101 and EVR-MOCK0001 are in both stores, and are Sara's
 * organisation's.
 */
describe('SCRUM-61 mock: a cancellation reaches the venue and equipment mocks', () => {
  const BOOKABLE = 'EVR-BOOK0101'
  /** EVR-MOCK0001's projector line, still waiting for its outcome. */
  const OPEN_LINE_ID = 41

  /** Chloe raises a venue booking request for BOOKABLE from `startsAt`; it starts Pending. */
  async function raiseVenueRequest(startsAt: string) {
    signInAs(CHLOE)
    const raised = await raiseBookingRequest(BOOKABLE, {
      venue_id: MOCK_BOOKING_VENUES.roomy.id,
      starts_at: startsAt,
      ends_at: '2026-11-10T17:00:00+08:00',
      purpose: 'Keynote',
    })
    return raised.id
  }

  it('releases an approved venue request and withdraws a pending one', async () => {
    const approvedId = await raiseVenueRequest('2026-11-10T09:00:00+08:00')
    const pendingId = await raiseVenueRequest('2026-11-10T13:00:00+08:00')
    signInAs(MOCK_ACCOUNTS.venueStaff)
    await decideBookingRequest(approvedId, { outcome: 'approved' })
    signInAs(SARA)

    await cancelEvent(BOOKABLE, { reason: REASON })

    signInAs(CHLOE)
    const statuses = (await fetchBookingRequests(BOOKABLE)).map((arrangement) => [
      arrangement.id,
      arrangement.status,
    ])
    expect(statuses).toEqual([
      [approvedId, 'released'],
      [pendingId, 'withdrawn'],
    ])
  })

  it('returns its reserved equipment and refuses an outcome on its open lines', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    await reserveEquipment(MOCK_OPEN_EVENT_REFERENCE, { equipment_type_id: 3, quantity: 1 })
    signInAs(SARA)

    await cancelEvent(MOCK_OPEN_EVENT_REFERENCE, { reason: REASON })

    signInAs(MOCK_ACCOUNTS.technicalSupport)
    expect(await fetchEventReservations(MOCK_OPEN_EVENT_REFERENCE)).toEqual([])
    const outcome = recordEquipmentOutcome(MOCK_OPEN_EVENT_REFERENCE, {
      lineId: OPEN_LINE_ID,
      body: { provided_quantity: 1 },
    })
    expect(await refusal(outcome)).toMatchObject({
      status: 409,
      code: 'conflict',
      message:
        "An equipment outcome can't be recorded for an event that is completed, cancelled or " +
        'rejected; this one is cancelled.',
    })
  })
})
