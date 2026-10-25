import { screen, waitFor, within } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'

import { coordinatorEventPath, organiserRequestPath } from '@/config/routes'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import { findRegion, serveRecordInStatus, statusShownFor } from '../test/recordPage'

/**
 * The assigned coordinator's planning actions on an event's page, each shown only in the status
 * the backend accepts it in, with the backend's refusals and every reason they give
 * (ADR-0075). The mock in src/mocks/handlers/eventPlanning.ts holds Hana's EVR-PLAN0001
 * (approved; arrangement 42 pending, equipment request 43 unanswered), EVR-PLAN0002 (approved
 * and settled), EVR-PLAN0003 (in Safety Review, approved by the Safety Officer and settled),
 * EVR-PLAN0004 (in Safety Review, not approved, arrangement 48 rejected, equipment request 49
 * unanswered), EVR-PLAN0005 (confirmed, ended; registration open for 50 with 30 registered,
 * though its organiser didn't ask for it) and EVR-PLAN0006 (confirmed, not yet ended; its
 * organiser asked for registration and nothing is set).
 */

const HANA = mockSessionFor(MOCK_ACCOUNTS.planningCoordinator)
const APPROVED_WITH_GAPS = 'EVR-PLAN0001'
const APPROVED_AND_SETTLED = 'EVR-PLAN0002'
const READY_TO_CONFIRM = 'EVR-PLAN0003'
const HELD_BACK_EVERYWHERE = 'EVR-PLAN0004'
const CONFIRMED_AND_ENDED = 'EVR-PLAN0005'
const CONFIRMED_NOT_ENDED = 'EVR-PLAN0006'

/** The actions each status offers; every status not named offers none. */
const OFFERED_BY_STATUS: [EventRequestStatus, string[]][] = [
  [EVENT_REQUEST_STATUS.APPROVED, ['Send to safety review', 'Reject event']],
  [EVENT_REQUEST_STATUS.SAFETY_REVIEW, ['Confirm event', 'Reject event']],
  [EVENT_REQUEST_STATUS.CONFIRMED, ['Save registration', 'Mark completed']],
]
const STATUSES_OFFERING_NOTHING = Object.values(EVENT_REQUEST_STATUS).filter(
  (status) => !OFFERED_BY_STATUS.some(([offering]) => offering === status),
)

function openAsHana(reference: string) {
  return renderApp(coordinatorEventPath(reference), { session: HANA })
}

/** The names of the buttons in the Planning section, in the order the page shows them. */
async function offeredActions(): Promise<string[]> {
  await screen.findByRole('region', { name: 'About the event' })
  const planning = screen.queryByRole('region', { name: 'Planning' })
  if (planning === null) {
    return []
  }
  return within(planning)
    .getAllByRole('button')
    .map((button) => button.textContent)
}

/** Answer every POST to `action` on `reference` with a 409 carrying `failure`. */
function refuseAction(reference: string, action: string, failure: object) {
  server.use(
    http.post(`/api/events/requests/${reference}/${action}`, () =>
      HttpResponse.json(failure, { status: 409 }),
    ),
  )
}

describe('SCRUM-97, SCRUM-68, SCRUM-69, SCRUM-49 the planning actions offered in each status', () => {
  it.each(OFFERED_BY_STATUS)('offers an event that is %s: %j', async (status, expected) => {
    await serveRecordInStatus(MOCK_ACCOUNTS.planningCoordinator, APPROVED_AND_SETTLED, status)
    openAsHana(APPROVED_AND_SETTLED)

    expect(await offeredActions()).toEqual(expected)
    expect(await findRegion('Planning')).toBeInTheDocument()
  })

  it.each(STATUSES_OFFERING_NOTHING)(
    'offers nothing, and no Planning section, for an event that is %s',
    async (status) => {
      await serveRecordInStatus(MOCK_ACCOUNTS.planningCoordinator, APPROVED_AND_SETTLED, status)
      openAsHana(APPROVED_AND_SETTLED)

      expect(await offeredActions()).toEqual([])
      expect(screen.queryByRole('region', { name: 'Planning' })).not.toBeInTheDocument()
    },
  )

  it('offers the organiser nothing on their copy of an approved event', async () => {
    renderApp(organiserRequestPath('EVR-W9CR5E7M'), {
      session: mockSessionFor(MOCK_ACCOUNTS.organiser),
    })

    expect(await offeredActions()).toEqual([])
    expect(screen.queryByRole('region', { name: 'Planning' })).not.toBeInTheDocument()
  })
})

describe('SCRUM-97 sending an event to safety review', () => {
  it('sends it, and the page shows the status the backend now gives', async () => {
    const requests = recordRequests()
    const { user } = openAsHana(APPROVED_AND_SETTLED)

    await user.click(await screen.findByRole('button', { name: 'Send to safety review' }))

    expect(await screen.findByText('Safety review')).toBeInTheDocument()
    expect(statusShownFor(APPROVED_AND_SETTLED)).toBe('Safety review')
    expect(screen.queryByRole('button', { name: 'Send to safety review' })).not.toBeInTheDocument()
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toMatch(
      new RegExp(`/api/events/requests/${APPROVED_AND_SETTLED}/safety-review$`),
    )
  })

  it('lists every gap the backend names, under its message', async () => {
    const { user } = openAsHana(APPROVED_WITH_GAPS)

    await user.click(await screen.findByRole('button', { name: 'Send to safety review' }))

    const card = await findRegion('Send to safety review')
    const alert = await within(card).findByRole('alert')
    expect(alert).toHaveTextContent(
      'The event can go to Safety Review once every venue arrangement is approved',
    )
    expect(
      within(alert)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual([
      'Venue arrangement 42 is pending.',
      'Equipment request 43 has no outcome from Technical Support.',
    ])
    expect(statusShownFor(APPROVED_WITH_GAPS)).toBe('Approved')
  })

  it("shows the backend's own words for a refusal, as they come", async () => {
    refuseAction(APPROVED_AND_SETTLED, 'safety-review', {
      error: 'safety_review_not_allowed',
      message: 'Not yet, says the backend.',
      details: { venue_arrangements: ['Only the backend could say this about venue 7.'] },
    })
    const { user } = openAsHana(APPROVED_AND_SETTLED)

    await user.click(await screen.findByRole('button', { name: 'Send to safety review' }))

    const alert = await within(await findRegion('Send to safety review')).findByRole('alert')
    expect(alert).toHaveTextContent('Not yet, says the backend.')
    expect(alert).toHaveTextContent('Only the backend could say this about venue 7.')
  })

  it('says it is busy while the event is being sent', async () => {
    server.use(
      http.post(`/api/events/requests/${APPROVED_AND_SETTLED}/safety-review`, () =>
        delay('infinite'),
      ),
    )
    const { user } = openAsHana(APPROVED_AND_SETTLED)
    const send = await screen.findByRole('button', { name: 'Send to safety review' })

    await user.click(send)

    expect(send).toBeDisabled()
    expect(send).toHaveAttribute('aria-busy', 'true')
  })
})

describe('SCRUM-68 marking an event completed', () => {
  it('completes an ended event, and the page shows Completed with nothing left to do', async () => {
    const requests = recordRequests()
    const { user } = openAsHana(CONFIRMED_AND_ENDED)

    await user.click(await screen.findByRole('button', { name: 'Mark completed' }))

    expect(await screen.findByText('Completed')).toBeInTheDocument()
    expect(statusShownFor(CONFIRMED_AND_ENDED)).toBe('Completed')
    expect(screen.queryByRole('region', { name: 'Planning' })).not.toBeInTheDocument()
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toMatch(new RegExp(`/api/events/requests/${CONFIRMED_AND_ENDED}/complete$`))
  })

  it("shows the backend's refusal for an event that hasn't ended", async () => {
    const { user } = openAsHana(CONFIRMED_NOT_ENDED)

    await user.click(await screen.findByRole('button', { name: 'Mark completed' }))

    const alert = await within(await findRegion('Mark completed')).findByRole('alert')
    expect(alert).toHaveTextContent('The event has not ended yet.')
    expect(statusShownFor(CONFIRMED_NOT_ENDED)).toBe('Confirmed')
  })

  it("shows the backend's own words for a refusal, as they come", async () => {
    refuseAction(CONFIRMED_AND_ENDED, 'complete', {
      error: 'request_not_completable',
      message: 'Only the backend could say this about completing.',
    })
    const { user } = openAsHana(CONFIRMED_AND_ENDED)

    await user.click(await screen.findByRole('button', { name: 'Mark completed' }))

    const alert = await within(await findRegion('Mark completed')).findByRole('alert')
    expect(alert).toHaveTextContent('Only the backend could say this about completing.')
  })
})

describe('SCRUM-69 registration settings', () => {
  /** The registration card, once the page has loaded. */
  function registrationCard() {
    return findRegion('Registration settings')
  }

  /** The body of the change the page sent. */
  async function sentChange(requests: Request[]): Promise<unknown> {
    const sent = requests.find((request) => request.method === 'PATCH')
    expect(sent?.url).toMatch(/\/api\/events\/requests\/EVR-PLAN000[56]\/registration$/)
    return sent?.json()
  }

  it.each([
    [CONFIRMED_NOT_ENDED, 'The organiser asked for registration.'],
    [CONFIRMED_AND_ENDED, 'The organiser did not ask for registration.'],
  ])(
    'starts %s with nothing chosen or typed, and nothing to save yet',
    async (reference, answer) => {
      openAsHana(reference)

      const card = await registrationCard()
      expect(card).toHaveTextContent(answer)
      expect(card).toHaveTextContent(
        'Pick one only to change it; left unpicked, registration stays as it is.',
      )
      expect(within(card).getByRole('radio', { name: 'Open' })).not.toBeChecked()
      expect(within(card).getByRole('radio', { name: 'Closed' })).not.toBeChecked()
      expect(within(card).getByLabelText('Capacity')).toHaveValue(null)
      expect(within(card).getByRole('button', { name: 'Save registration' })).toBeDisabled()
    },
  )

  it('keeps registration open when only a new capacity is saved, sending just the capacity', async () => {
    const requests = recordRequests()
    const { user } = openAsHana(CONFIRMED_AND_ENDED)
    const card = await registrationCard()

    await user.type(within(card).getByLabelText('Capacity'), '60')
    await user.click(within(card).getByRole('button', { name: 'Save registration' }))

    expect(await within(card).findByRole('status')).toHaveTextContent(
      'Registration is open. Capacity: 60.',
    )
    expect(await sentChange(requests)).toEqual({ registration_capacity: 60 })
  })

  it('opens registration with the capacity typed when Open is picked, sending both', async () => {
    const requests = recordRequests()
    const { user } = openAsHana(CONFIRMED_NOT_ENDED)
    const card = await registrationCard()

    await user.click(within(card).getByRole('radio', { name: 'Open' }))
    await user.type(within(card).getByLabelText('Capacity'), '120')
    await user.click(within(card).getByRole('button', { name: 'Save registration' }))

    expect(await within(card).findByRole('status')).toHaveTextContent(
      'Registration is open. Capacity: 120.',
    )
    expect(await sentChange(requests)).toEqual({
      registration_enabled: true,
      registration_capacity: 120,
    })
  })

  it("closes registration when Closed is picked, sending no capacity, so the event's is kept", async () => {
    const requests = recordRequests()
    const { user } = openAsHana(CONFIRMED_AND_ENDED)
    const card = await registrationCard()

    await user.click(within(card).getByRole('radio', { name: 'Closed' }))
    await user.click(within(card).getByRole('button', { name: 'Save registration' }))

    expect(await within(card).findByRole('status')).toHaveTextContent(
      'Registration is closed. Capacity: 50.',
    )
    expect(await sentChange(requests)).toEqual({ registration_enabled: false })
  })

  it("shows the backend's message under the capacity when opening without one", async () => {
    const { user } = openAsHana(CONFIRMED_NOT_ENDED)
    const card = await registrationCard()

    await user.click(within(card).getByRole('radio', { name: 'Open' }))
    await user.click(within(card).getByRole('button', { name: 'Save registration' }))

    expect(await within(card).findByRole('alert')).toHaveTextContent('Invalid request.')
    expect(within(card).getByLabelText('Capacity')).toHaveAccessibleDescription(
      'A capacity is required to enable registration.',
    )
    expect(within(card).queryByRole('status')).not.toBeInTheDocument()
  })

  it('opens registration as chosen, and shows the refusal of a capacity below the places taken', async () => {
    const requests = recordRequests()
    const { user } = openAsHana(CONFIRMED_AND_ENDED)
    const card = await registrationCard()

    await user.click(within(card).getByRole('radio', { name: 'Open' }))
    await user.type(within(card).getByLabelText('Capacity'), '20')
    await user.click(within(card).getByRole('button', { name: 'Save registration' }))

    await within(card).findByRole('alert')
    expect(within(card).getByLabelText('Capacity')).toHaveAccessibleDescription(
      'Capacity cannot be lower than the 30 places already taken.',
    )
    expect(await sentChange(requests)).toEqual({
      registration_enabled: true,
      registration_capacity: 20,
    })
  })

  it('says only that registration is closed when the event has no capacity', async () => {
    const { user } = openAsHana(CONFIRMED_NOT_ENDED)
    const card = await registrationCard()

    await user.click(within(card).getByRole('radio', { name: 'Closed' }))
    await user.click(within(card).getByRole('button', { name: 'Save registration' }))

    expect(await within(card).findByRole('status')).toHaveTextContent(/^Registration is closed\.$/)
  })

  it('stops saying what was saved once a later save is refused', async () => {
    const { user } = openAsHana(CONFIRMED_AND_ENDED)
    const card = await registrationCard()
    await user.click(within(card).getByRole('radio', { name: 'Closed' }))
    await user.click(within(card).getByRole('button', { name: 'Save registration' }))
    await within(card).findByRole('status')

    await user.type(within(card).getByLabelText('Capacity'), '20')
    await user.click(within(card).getByRole('button', { name: 'Save registration' }))

    await within(card).findByRole('alert')
    expect(within(card).queryByRole('status')).not.toBeInTheDocument()
  })

  it('sends the number as typed and leaves whole-number checks to the backend', async () => {
    const requests = recordRequests()
    const { user } = openAsHana(CONFIRMED_NOT_ENDED)
    const card = await registrationCard()

    await user.type(within(card).getByLabelText('Capacity'), '1.5')
    await user.click(within(card).getByRole('button', { name: 'Save registration' }))

    await within(card).findByRole('alert')
    expect(within(card).getByLabelText('Capacity')).toHaveAccessibleDescription(
      'Not a valid integer.',
    )
    expect(await sentChange(requests)).toEqual({ registration_capacity: 1.5 })
  })

  it("shows the backend's own words for a refusal, as they come", async () => {
    server.use(
      http.patch(`/api/events/requests/${CONFIRMED_NOT_ENDED}/registration`, () =>
        HttpResponse.json(
          {
            error: 'registration_not_enablable',
            message: 'Only the backend could say this about registration.',
          },
          { status: 409 },
        ),
      ),
    )
    const { user } = openAsHana(CONFIRMED_NOT_ENDED)
    const card = await registrationCard()

    await user.type(within(card).getByLabelText('Capacity'), '120')
    await user.click(within(card).getByRole('button', { name: 'Save registration' }))

    expect(await within(card).findByRole('alert')).toHaveTextContent(
      'Only the backend could say this about registration.',
    )
  })

  it('says it is busy while the settings are being saved', async () => {
    server.use(
      http.patch(`/api/events/requests/${CONFIRMED_NOT_ENDED}/registration`, () =>
        delay('infinite'),
      ),
    )
    const { user } = openAsHana(CONFIRMED_NOT_ENDED)
    const card = await registrationCard()
    const save = within(card).getByRole('button', { name: 'Save registration' })

    await user.type(within(card).getByLabelText('Capacity'), '120')
    await user.click(save)

    expect(save).toBeDisabled()
    expect(save).toHaveAttribute('aria-busy', 'true')
  })
})

describe('SCRUM-49 confirming an event', () => {
  it('confirms it, and the page shows Confirmed with what a confirmed event offers', async () => {
    const requests = recordRequests()
    const { user } = openAsHana(READY_TO_CONFIRM)

    await user.click(await screen.findByRole('button', { name: 'Confirm event' }))

    expect(await screen.findByRole('button', { name: 'Mark completed' })).toBeInTheDocument()
    expect(statusShownFor(READY_TO_CONFIRM)).toBe('Confirmed')
    expect(screen.queryByRole('button', { name: 'Confirm event' })).not.toBeInTheDocument()
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toMatch(new RegExp(`/api/events/requests/${READY_TO_CONFIRM}/confirm$`))
  })

  it('lists every approval still missing, in the order the backend gives them', async () => {
    const { user } = openAsHana(HELD_BACK_EVERYWHERE)

    await user.click(await screen.findByRole('button', { name: 'Confirm event' }))

    const alert = await within(await findRegion('Confirm the event')).findByRole('alert')
    expect(alert).toHaveTextContent(
      'The event can be confirmed once the Safety Officer has approved it',
    )
    expect(
      within(alert)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual([
      'The Safety Officer has not approved the event.',
      'Venue arrangement 48 is rejected.',
      'Equipment request 49 has no outcome from Technical Support.',
    ])
    expect(statusShownFor(HELD_BACK_EVERYWHERE)).toBe('Safety review')
  })

  it("shows the backend's own words for a refusal, as they come", async () => {
    refuseAction(READY_TO_CONFIRM, 'confirm', {
      error: 'confirmation_not_allowed',
      message: 'Not yet, says the backend.',
      details: { safety_check: ['Only the backend could say this about the safety check.'] },
    })
    const { user } = openAsHana(READY_TO_CONFIRM)

    await user.click(await screen.findByRole('button', { name: 'Confirm event' }))

    const alert = await within(await findRegion('Confirm the event')).findByRole('alert')
    expect(alert).toHaveTextContent('Not yet, says the backend.')
    expect(alert).toHaveTextContent('Only the backend could say this about the safety check.')
  })
})

describe('SCRUM-49 rejecting an event during planning (AC9, AC10)', () => {
  const REASON = 'No venue large enough is free that week.'

  /** Open the event and press Reject event, so the page asks whether to go ahead. */
  async function startRejecting(reference: string) {
    const opened = openAsHana(reference)
    await opened.user.click(await screen.findByRole('button', { name: 'Reject event' }))
    return opened
  }

  it('asks first, saying what is released, and sends nothing when the coordinator keeps planning', async () => {
    const requests = recordRequests()
    const { user } = await startRejecting(APPROVED_WITH_GAPS)

    const card = await findRegion('Reject the event')
    expect(card).toHaveTextContent(
      'Its venue bookings and holds are released and its equipment returned.',
    )
    await user.click(within(card).getByRole('button', { name: 'Keep planning' }))

    expect(within(card).getByRole('button', { name: 'Reject event' })).toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: 'Yes, reject the event' })).toBeNull()
    expect(requests.filter((request) => request.method === 'POST')).toEqual([])
    expect(statusShownFor(APPROVED_WITH_GAPS)).toBe('Approved')
  })

  it.each([APPROVED_WITH_GAPS, HELD_BACK_EVERYWHERE])(
    'rejects %s with the reason typed, and the page shows Rejected with nothing left to plan',
    async (reference) => {
      const requests = recordRequests()
      const { user } = openAsHana(reference)
      await user.type(await screen.findByLabelText('Reason for rejecting'), REASON)

      await user.click(screen.getByRole('button', { name: 'Reject event' }))
      await user.click(screen.getByRole('button', { name: 'Yes, reject the event' }))

      await waitFor(() => expect(statusShownFor(reference)).toBe('Rejected'))
      expect(screen.queryByRole('region', { name: 'Planning' })).not.toBeInTheDocument()
      const sent = requests.find((request) => request.method === 'POST')
      expect(sent?.url).toMatch(new RegExp(`/api/events/requests/${reference}/reject$`))
      expect(await sent?.json()).toEqual({ reason: REASON })
    },
  )

  it("sends no reason when none is typed, and shows the backend's message under the box", async () => {
    const requests = recordRequests()
    const { user } = await startRejecting(APPROVED_AND_SETTLED)

    await user.click(screen.getByRole('button', { name: 'Yes, reject the event' }))

    const reason = await screen.findByLabelText('Reason for rejecting')
    expect(await screen.findByText('A reason is required to reject the event.')).toBeInTheDocument()
    expect(reason).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('button', { name: 'Reject event' })).toBeInTheDocument()
    expect(statusShownFor(APPROVED_AND_SETTLED)).toBe('Approved')
    const sent = requests.find((request) => request.method === 'POST')
    expect(await sent?.json()).toEqual({})
  })

  it("shows the backend's own words for a refusal, as they come", async () => {
    refuseAction(READY_TO_CONFIRM, 'reject', {
      error: 'rejection_not_allowed',
      message: 'Not now, says the backend.',
    })
    const { user } = openAsHana(READY_TO_CONFIRM)
    await user.type(await screen.findByLabelText('Reason for rejecting'), REASON)

    await user.click(screen.getByRole('button', { name: 'Reject event' }))
    await user.click(screen.getByRole('button', { name: 'Yes, reject the event' }))

    const alert = await within(await findRegion('Reject the event')).findByRole('alert')
    expect(alert).toHaveTextContent('Not now, says the backend.')
  })

  it("refuses a new decision afterwards in the backend's words, and reads the event again (AC12)", async () => {
    const { user } = openAsHana(READY_TO_CONFIRM)
    await user.type(await screen.findByLabelText('Reason for rejecting'), REASON)
    await user.click(screen.getByRole('button', { name: 'Reject event' }))
    await user.click(screen.getByRole('button', { name: 'Yes, reject the event' }))
    await waitFor(() => expect(statusShownFor(READY_TO_CONFIRM)).toBe('Rejected'))
    const requests = recordRequests()

    await user.type(await screen.findByLabelText('Reason'), 'A larger hall came free.')
    await user.click(screen.getByRole('button', { name: 'Approve' }))

    const alert = await within(await findRegion('Decide')).findByRole('alert')
    expect(alert).toHaveTextContent(
      "The decision can't be changed once the event has been rejected during planning. " +
        'To go ahead, the organiser submits a new event request.',
    )
    expect(statusShownFor(READY_TO_CONFIRM)).toBe('Rejected')
    await waitFor(() =>
      expect(
        requests.some(
          (request) =>
            request.method === 'GET' &&
            request.url.endsWith(`/api/events/requests/${READY_TO_CONFIRM}`),
        ),
      ).toBe(true),
    )
  })

  it('says it is busy while the event is being rejected', async () => {
    server.use(
      http.post(`/api/events/requests/${APPROVED_AND_SETTLED}/reject`, () => delay('infinite')),
    )
    const { user } = await startRejecting(APPROVED_AND_SETTLED)
    const reject = screen.getByRole('button', { name: 'Yes, reject the event' })

    await user.click(reject)

    expect(reject).toBeDisabled()
    expect(reject).toHaveAttribute('aria-busy', 'true')
  })
})
