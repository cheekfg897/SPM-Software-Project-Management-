import { withdrawFromEvent } from '@/features/catalogue/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'

/**
 * SCRUM-53: withdrawing a registration against the real backend (docs/adr/0032 *Withdrawing*).
 *
 * These check every refusal the backend gives an attendee who holds no place. Holding one needs an
 * event taken through safety review, confirmed and opened for registration; the steps to do that
 * live in planning.int.test.ts, so the checks that need a registration wait below as todos until
 * those steps are shared. The mock handlers stand in for them until then.
 */

/** An id no event has, so there is no registration for it. */
const MISSING_EVENT_ID = 2_000_000_000

afterEach(() => sendRequestsAs(null))

describe('SCRUM-53 withdrawing against the backend', () => {
  it('refuses a visitor (401) and another role (403)', async () => {
    const visitor = await refusal(withdrawFromEvent(MISSING_EVENT_ID))
    await signInAs(staffAccount())
    const coordinator = await refusal(withdrawFromEvent(MISSING_EVENT_ID))

    expect(visitor).toMatchObject({ status: 401, code: 'authentication_error' })
    expect(coordinator).toMatchObject({
      status: 403,
      code: 'authorization_error',
      message: 'You do not have permission to perform this action.',
    })
  })

  it('answers 404 for an event the attendee holds no registration for', async () => {
    await signInAsNewAttendee()

    const error = await refusal(withdrawFromEvent(MISSING_EVENT_ID))

    expect(error).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Registration not found.',
    })
    expect(error.details).toEqual({})
  })

  // These need a registration, which needs a confirmed event with registration enabled.
  it.todo('withdraws a held place (200), answering with status withdrawn and withdrawn_at')
  it.todo('gives the place back to places_left and lists the registration as withdrawn')
  it.todo('refuses a second withdrawal (409 already_withdrawn)')
  it.todo(
    'refuses once the event has started (409 withdrawal_closed) with details.withdrawal_closed_at',
  )
})
