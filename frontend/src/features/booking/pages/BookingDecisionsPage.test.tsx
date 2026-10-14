import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { REJECTION_REASON_REQUIRED_MESSAGE } from '@/mocks/handlers/booking'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

const QUEUE_URL = '/api/venues/booking-requests'

/** The queue entry for one request, found by the purpose its heading gives it. */
async function findRequest(purpose: string) {
  return within(await screen.findByRole('article', { name: purpose }))
}

function renderQueue() {
  return renderApp(ROUTES.BOOKING_DECISIONS, {
    session: mockSessionFor(MOCK_ACCOUNTS.venueStaff),
  })
}

describe('SCRUM-43 the venue booking decisions screen', () => {
  it('shows each waiting request with its own details and its event timing', async () => {
    renderQueue()

    const breakout = await findRequest('Breakout room')
    expect(breakout.getByText(/Venue 1/)).toBeInTheDocument()
    expect(breakout.getByText(/40 guests/)).toBeInTheDocument()
    expect(breakout.getByText(/Classroom/)).toBeInTheDocument()
    expect(breakout.getByText(/2026-11-20/)).toBeInTheDocument()
    expect(breakout.getByText(/Step-free access/)).toBeInTheDocument()
  })

  it('lists the earliest event first, whatever order the requests were raised in', async () => {
    renderQueue()
    await findRequest('Breakout room')

    const purposes = screen.getAllByRole('heading', { level: 3 }).map((entry) => entry.textContent)

    expect(purposes).toEqual(['Breakout room', 'Main hall'])
  })

  it('sends the approval and takes the request out of the queue', async () => {
    const requests = recordRequests()
    const { user } = renderQueue()
    const breakout = await findRequest('Breakout room')

    await user.click(breakout.getByRole('button', { name: /^Approve/ }))

    await waitFor(() => expect(screen.queryByRole('article', { name: 'Breakout room' })).toBeNull())
    const decision = requests.find((sent) => sent.method === 'POST')
    expect(decision?.url).toContain(`${QUEUE_URL}/9001/decision`)
    await expect(decision?.json()).resolves.toEqual({ outcome: 'approved' })
    expect(await screen.findByRole('article', { name: 'Main hall' })).toBeInTheDocument()
  })

  it('shows the backend field error when a rejection has no reason', async () => {
    const { user } = renderQueue()
    const breakout = await findRequest('Breakout room')

    await user.click(breakout.getByRole('button', { name: /^Reject/ }))

    expect(await breakout.findByText(REJECTION_REASON_REQUIRED_MESSAGE)).toBeInTheDocument()
    expect(screen.getByRole('article', { name: 'Breakout room' })).toBeInTheDocument()
  })

  it('sends the reason with a rejection and takes the request out of the queue', async () => {
    const requests = recordRequests()
    const { user } = renderQueue()
    const breakout = await findRequest('Breakout room')

    await user.type(breakout.getByLabelText(/^Reason/), 'Closed for repairs')
    await user.click(breakout.getByRole('button', { name: /^Reject/ }))

    await waitFor(() => expect(screen.queryByRole('article', { name: 'Breakout room' })).toBeNull())
    const decision = requests.find((sent) => sent.method === 'POST')
    await expect(decision?.json()).resolves.toEqual({
      outcome: 'rejected',
      reason: 'Closed for repairs',
    })
  })

  it('says so when nothing is waiting for a decision', async () => {
    server.use(http.get(QUEUE_URL, () => HttpResponse.json([])))
    renderQueue()

    expect(await screen.findByText(/No booking requests are waiting/)).toBeInTheDocument()
  })

  it('shows the backend error and reads the queue again when asked', async () => {
    server.use(
      http.get(QUEUE_URL, () =>
        HttpResponse.json(
          { error: 'server_error', message: 'The venue service is unavailable.' },
          { status: 500 },
        ),
      ),
    )
    const { user } = renderQueue()

    expect(await screen.findByText('The venue service is unavailable.')).toBeInTheDocument()
    server.use(http.get(QUEUE_URL, () => HttpResponse.json([])))
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText(/No booking requests are waiting/)).toBeInTheDocument()
  })

  it('sends a coordinator to the staff home rather than the queue', async () => {
    const { router } = renderQueue()
    await screen.findByRole('article', { name: 'Breakout room' })

    const coordinator = renderApp(ROUTES.BOOKING_DECISIONS, {
      session: mockSessionFor(MOCK_ACCOUNTS.coordinator),
    })

    await waitFor(() => expect(coordinator.router.state.location.pathname).toBe(ROUTES.STAFF_HOME))
    expect(router.state.location.pathname).toBe(ROUTES.BOOKING_DECISIONS)
  })
})
