import { screen, within } from '@testing-library/react'
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
 * (approved; arrangement 42 pending, equipment request 43 unanswered) and EVR-PLAN0002 (approved
 * and settled).
 */

const HANA = mockSessionFor(MOCK_ACCOUNTS.planningCoordinator)
const APPROVED_WITH_GAPS = 'EVR-PLAN0001'
const APPROVED_AND_SETTLED = 'EVR-PLAN0002'
const ACTION_BUTTONS = ['Send to safety review']

/** The actions each status offers; every status not named offers none. */
const OFFERED_BY_STATUS: [EventRequestStatus, string[]][] = [
  [EVENT_REQUEST_STATUS.APPROVED, ['Send to safety review']],
]
const STATUSES_OFFERING_NOTHING = Object.values(EVENT_REQUEST_STATUS).filter(
  (status) => !OFFERED_BY_STATUS.some(([offering]) => offering === status),
)

function openAsHana(reference: string) {
  return renderApp(coordinatorEventPath(reference), { session: HANA })
}

/** The names of the planning buttons the page offers, in order. */
async function offeredActions(): Promise<string[]> {
  await screen.findByRole('region', { name: 'About the event' })
  return ACTION_BUTTONS.filter((name) => screen.queryByRole('button', { name }) !== null)
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
