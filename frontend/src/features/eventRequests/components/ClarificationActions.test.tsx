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
 * SCRUM-32 AC1, AC2, AC4: the assigned coordinator asks the organiser a question from the
 * event's page, and the organiser answers it on theirs; both stay on the record (ADR-0060). The
 * mock in src/mocks/handlers/eventRequests.ts holds Priya's EVR-RV2D5F8J (under review) and
 * Omar's EVR-B6YF2K8V, which Chloe coordinates, awaiting an answer to its second question. Its
 * "now" is 5 Oct, 12:00 pm.
 */

const PRIYAS_UNDER_REVIEW = 'EVR-RV2D5F8J'
const AWAITING_ANSWER = 'EVR-B6YF2K8V'
const OPEN_QUESTION = 'Can the start move to 2pm so the vans can unload first?'
const OMAR = MOCK_ACCOUNTS.organiser
const NON_AWAITING_STATUSES = Object.values(EVENT_REQUEST_STATUS).filter(
  (status) => status !== EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
)

function openAsOmar(reference: string) {
  return renderApp(organiserRequestPath(reference), { session: mockSessionFor(OMAR) })
}

/** Omar's request awaiting an answer, as the backend would send it in `status`. */
function serveAwaitingAs(status: EventRequestStatus) {
  return serveRecordInStatus(OMAR, AWAITING_ANSWER, status)
}

describe('SCRUM-32 AC1, AC4 asking the organiser a question', () => {
  function openAsPriya() {
    return renderApp(coordinatorEventPath(PRIYAS_UNDER_REVIEW), {
      session: mockSessionFor(MOCK_ACCOUNTS.reviewingCoordinator),
    })
  }

  it('sends the question, and the page shows it waiting for an answer', async () => {
    const requests = recordRequests()
    const { user } = openAsPriya()

    await user.type(await screen.findByLabelText('Question'), 'Is the room step-free?')
    await user.click(screen.getByRole('button', { name: 'Ask for clarification' }))

    const clarifications = await findRegion('Clarifications')
    expect(clarifications).toHaveTextContent('Is the room step-free?')
    expect(clarifications).toHaveTextContent('Asked by Priya Nair, 5 Oct, 12:00 pm')
    expect(clarifications).toHaveTextContent('Waiting for an answer.')
    expect(statusShownFor(PRIYAS_UNDER_REVIEW)).toBe('Awaiting clarification')
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toMatch(
      new RegExp(`/api/events/requests/${PRIYAS_UNDER_REVIEW}/request-clarification$`),
    )
    await expect(sent?.json()).resolves.toEqual({ message: 'Is the room step-free?' })
  })

  it('no longer offers a question or an approval once one is outstanding (AC3)', async () => {
    const { user } = openAsPriya()

    await user.type(await screen.findByLabelText('Question'), 'Is the room step-free?')
    await user.click(screen.getByRole('button', { name: 'Ask for clarification' }))

    await findRegion('Clarifications')
    expect(screen.queryByLabelText('Question')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
  })

  it("shows the backend's message under the box for a blank question, keeping what was typed", async () => {
    const { user } = openAsPriya()

    await user.type(await screen.findByLabelText('Question'), '   ')
    await user.click(screen.getByRole('button', { name: 'Ask for clarification' }))

    expect(await screen.findByText('Must not be blank.')).toBeInTheDocument()
    expect(screen.getByLabelText('Question')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Question')).toHaveValue('   ')
    expect(statusShownFor(PRIYAS_UNDER_REVIEW)).toBe('Under review')
  })

  it("shows the backend's refusal above the box", async () => {
    server.use(
      http.post(`/api/events/requests/${PRIYAS_UNDER_REVIEW}/request-clarification`, () =>
        HttpResponse.json(
          { error: 'clarification_not_allowed', message: 'Not now, says the backend.' },
          { status: 409 },
        ),
      ),
    )
    const { user } = openAsPriya()

    await user.type(await screen.findByLabelText('Question'), 'Is the room step-free?')
    await user.click(screen.getByRole('button', { name: 'Ask for clarification' }))

    const ask = await findRegion('Ask the organiser')
    expect(await within(ask).findByRole('alert')).toHaveTextContent('Not now, says the backend.')
  })

  it('says it is busy while the question is being sent', async () => {
    server.use(
      http.post(`/api/events/requests/${PRIYAS_UNDER_REVIEW}/request-clarification`, () =>
        delay('infinite'),
      ),
    )
    const { user } = openAsPriya()
    const ask = await screen.findByRole('button', { name: 'Ask for clarification' })

    await user.click(ask)

    expect(ask).toBeDisabled()
    expect(ask).toHaveAttribute('aria-busy', 'true')
  })
})

describe('SCRUM-32 AC2, AC4 the organiser answering', () => {
  it('sends only the answer, and the page shows it under the question, back under review', async () => {
    const requests = recordRequests()
    const { user } = openAsOmar(AWAITING_ANSWER)

    await user.type(await screen.findByLabelText('Your answer'), 'Yes, 2pm works.')
    await user.click(screen.getByRole('button', { name: 'Send answer' }))

    expect(await screen.findByText('Answered by Omar Rahman, 5 Oct, 12:00 pm')).toBeInTheDocument()
    const clarifications = await findRegion('Clarifications')
    const open = within(clarifications).getAllByRole('listitem')[1]
    expect(open).toHaveTextContent(OPEN_QUESTION)
    expect(open).toHaveTextContent('Yes, 2pm works.')
    expect(statusShownFor(AWAITING_ANSWER)).toBe('Under review')
    expect(screen.queryByLabelText('Your answer')).not.toBeInTheDocument()
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toMatch(new RegExp(`/api/events/requests/${AWAITING_ANSWER}/resubmit$`))
    await expect(sent?.json()).resolves.toEqual({ response: 'Yes, 2pm works.' })
  })

  it("shows the backend's message under the box for a blank answer", async () => {
    const { user } = openAsOmar(AWAITING_ANSWER)

    await user.click(await screen.findByRole('button', { name: 'Send answer' }))

    expect(await screen.findByText('Must not be blank.')).toBeInTheDocument()
    expect(screen.getByLabelText('Your answer')).toHaveAttribute('aria-invalid', 'true')
    expect(statusShownFor(AWAITING_ANSWER)).toBe('Awaiting clarification')
  })

  it.each(NON_AWAITING_STATUSES)(
    'offers no answer box for a request that is %s',
    async (status) => {
      await serveAwaitingAs(status)
      openAsOmar(AWAITING_ANSWER)

      await findRegion('Clarifications')
      expect(screen.queryByLabelText('Your answer')).not.toBeInTheDocument()
    },
  )

  it('offers the answer box to the organiser only, not the coordinator', async () => {
    renderApp(coordinatorEventPath(AWAITING_ANSWER), {
      session: mockSessionFor(MOCK_ACCOUNTS.coordinator),
    })

    await findRegion('Clarifications')
    expect(screen.queryByLabelText('Your answer')).not.toBeInTheDocument()
  })
})
