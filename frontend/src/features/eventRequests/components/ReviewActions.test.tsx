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
 * SCRUM-31 AC3, AC4, AC6, AC7: the assigned coordinator starts a review and decides a request
 * from its page, each action shown only in the statuses it can apply to, with the backend's
 * refusals shown as they come (ADR-0060). The mock in src/mocks/handlers/eventRequests.ts holds
 * Priya's EVR-RV4K8N2P (submitted), EVR-RV7T3M5Q (approved, decision locked) and EVR-RV9H6C1W
 * (rejected), and Chloe's EVR-B6YF2K8V (awaiting clarification). Its "now" is 5 Oct, 12:00 pm.
 */

const PRIYA = mockSessionFor(MOCK_ACCOUNTS.reviewingCoordinator)
const SUBMITTED = 'EVR-RV4K8N2P'
const LOCKED_APPROVED = 'EVR-RV7T3M5Q'
const REJECTED = 'EVR-RV9H6C1W'
const ACTION_BUTTONS = ['Start review', 'Approve', 'Reject', 'Ask for clarification']

function openAsPriya(reference: string) {
  return renderApp(coordinatorEventPath(reference), { session: PRIYA })
}

/** The names of the review buttons the page offers, in order. */
async function offeredActions(): Promise<string[]> {
  await screen.findByRole('region', { name: 'About the event' })
  return ACTION_BUTTONS.filter((name) => screen.queryByRole('button', { name }) !== null)
}

/** Priya's submitted request, as the backend would send it in `status`. */
function serveSubmittedAs(status: EventRequestStatus) {
  return serveRecordInStatus(MOCK_ACCOUNTS.reviewingCoordinator, SUBMITTED, status)
}

describe('SCRUM-31, SCRUM-32 the review actions offered in each status', () => {
  it.each<[EventRequestStatus, string[]]>([
    [EVENT_REQUEST_STATUS.SUBMITTED, ['Start review', 'Approve', 'Reject']],
    [EVENT_REQUEST_STATUS.UNDER_REVIEW, ['Approve', 'Reject', 'Ask for clarification']],
    [EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION, ['Reject']],
    [EVENT_REQUEST_STATUS.APPROVED, ['Approve', 'Reject']],
    [EVENT_REQUEST_STATUS.REJECTED, ['Approve', 'Reject']],
  ])('offers a request that is %s: %j', async (status, expected) => {
    await serveSubmittedAs(status)
    openAsPriya(SUBMITTED)

    expect(await offeredActions()).toEqual(expected)
    expect(await findRegion('Review')).toBeInTheDocument()
  })

  it.each([
    EVENT_REQUEST_STATUS.DRAFT,
    EVENT_REQUEST_STATUS.SAFETY_REVIEW,
    EVENT_REQUEST_STATUS.CONFIRMED,
    EVENT_REQUEST_STATUS.COMPLETED,
    EVENT_REQUEST_STATUS.CANCELLED,
  ])('offers nothing, and no Review section, for a request that is %s', async (status) => {
    await serveSubmittedAs(status)
    openAsPriya(SUBMITTED)

    expect(await offeredActions()).toEqual([])
    expect(screen.queryByRole('region', { name: 'Review' })).not.toBeInTheDocument()
  })

  it('offers the organiser nothing on their copy of the page', async () => {
    renderApp(organiserRequestPath('EVR-7K2M9QXA'), {
      session: mockSessionFor(MOCK_ACCOUNTS.organiser),
    })

    expect(await offeredActions()).toEqual([])
    expect(screen.queryByRole('region', { name: 'Review' })).not.toBeInTheDocument()
  })
})

describe('SCRUM-31 AC3 starting a review', () => {
  it('moves the request to under review, and the page shows what the backend now says', async () => {
    const requests = recordRequests()
    const { user } = openAsPriya(SUBMITTED)

    await user.click(await screen.findByRole('button', { name: 'Start review' }))

    expect(await screen.findByText('Under review')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start review' })).not.toBeInTheDocument()
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toMatch(new RegExp(`/api/events/requests/${SUBMITTED}/review$`))
  })

  it("shows the backend's refusal", async () => {
    server.use(
      http.post(`/api/events/requests/${SUBMITTED}/review`, () =>
        HttpResponse.json(
          {
            error: 'request_not_reviewable',
            message: 'Only a submitted request, says the backend.',
          },
          { status: 409 },
        ),
      ),
    )
    const { user } = openAsPriya(SUBMITTED)

    await user.click(await screen.findByRole('button', { name: 'Start review' }))

    const start = await findRegion('Start the review')
    expect(await within(start).findByRole('alert')).toHaveTextContent(
      'Only a submitted request, says the backend.',
    )
  })

  it('says it is busy while the review is starting', async () => {
    server.use(http.post(`/api/events/requests/${SUBMITTED}/review`, () => delay('infinite')))
    const { user } = openAsPriya(SUBMITTED)
    const start = await screen.findByRole('button', { name: 'Start review' })

    await user.click(start)

    expect(start).toBeDisabled()
    expect(start).toHaveAttribute('aria-busy', 'true')
  })
})

describe('SCRUM-31 AC4, AC6 deciding', () => {
  it('approves without a reason, sending only the outcome, and shows the decision', async () => {
    const requests = recordRequests()
    const { user } = openAsPriya(SUBMITTED)

    await user.click(await screen.findByRole('button', { name: 'Approve' }))

    const decision = await findRegion('Decision')
    expect(within(decision).getByText('Approved')).toBeInTheDocument()
    expect(within(decision).getByText('Decided by Priya Nair, 5 Oct, 12:00 pm')).toBeInTheDocument()
    expect(statusShownFor(SUBMITTED)).toBe('Approved')
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toMatch(new RegExp(`/api/events/requests/${SUBMITTED}/decide$`))
    await expect(sent?.json()).resolves.toEqual({ outcome: 'approved' })
  })

  it('rejects with the reason typed, then empties the box', async () => {
    const requests = recordRequests()
    const { user } = openAsPriya(SUBMITTED)
    const reason = await screen.findByLabelText('Reason')

    await user.type(reason, 'The hall is booked that week.')
    await user.click(screen.getByRole('button', { name: 'Reject' }))

    const decision = await findRegion('Decision')
    expect(within(decision).getByText('The hall is booked that week.')).toBeInTheDocument()
    expect(statusShownFor(SUBMITTED)).toBe('Rejected')
    expect(screen.getByLabelText('Reason')).toHaveValue('')
    const sent = requests.find((request) => request.method === 'POST')
    await expect(sent?.json()).resolves.toEqual({
      outcome: 'rejected',
      reason: 'The hall is booked that week.',
    })
  })

  it("shows the backend's message under the box when a rejection has no reason", async () => {
    const { user } = openAsPriya(SUBMITTED)

    await user.click(await screen.findByRole('button', { name: 'Reject' }))

    const reason = screen.getByLabelText('Reason')
    expect(
      await screen.findByText('A reason is required to reject a request or to change a decision.'),
    ).toBeInTheDocument()
    expect(reason).toHaveAttribute('aria-invalid', 'true')
    expect(statusShownFor(SUBMITTED)).toBe('Submitted')
  })

  it('keeps the reason typed when the backend refuses it', async () => {
    const { user } = openAsPriya(LOCKED_APPROVED)

    await user.type(await screen.findByLabelText('Reason'), 'Too late now.')
    await user.click(screen.getByRole('button', { name: 'Reject' }))

    await screen.findByRole('alert')
    expect(screen.getByLabelText('Reason')).toHaveValue('Too late now.')
  })

  it("offers a change of a decision that is locked, and shows the backend's refusal (AC7)", async () => {
    const { user } = openAsPriya(LOCKED_APPROVED)

    await user.type(await screen.findByLabelText('Reason'), 'Too late now.')
    await user.click(screen.getByRole('button', { name: 'Reject' }))

    const decide = await findRegion('Decide')
    expect(await within(decide).findByRole('alert')).toHaveTextContent(
      "The decision can't be changed once the event has an equipment request or a venue booking request.",
    )
    expect(statusShownFor(LOCKED_APPROVED)).toBe('Approved')
  })

  it('changes a rejection to an approval with a reason (AC6)', async () => {
    const { user } = openAsPriya(REJECTED)

    await user.type(await screen.findByLabelText('Reason'), 'The atrium reopened.')
    await user.click(screen.getByRole('button', { name: 'Approve' }))

    const decision = await findRegion('Decision')
    expect(await within(decision).findByText('The atrium reopened.')).toBeInTheDocument()
    expect(within(decision).getByText('Approved')).toBeInTheDocument()
  })

  it('says it is busy while the decision is being sent', async () => {
    server.use(http.post(`/api/events/requests/${SUBMITTED}/decide`, () => delay('infinite')))
    const { user } = openAsPriya(SUBMITTED)
    const approve = await screen.findByRole('button', { name: 'Approve' })

    await user.click(approve)

    expect(approve).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled()
  })
})
