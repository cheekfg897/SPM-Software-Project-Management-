import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import {
  EXPIRY_NOT_BEFORE_EVENT_MESSAGE,
  REJECTION_REASON_REQUIRED_MESSAGE,
  SINGLE_VENUE_HOLD_MESSAGE,
} from '@/mocks/handlers/booking'
import { MOCK_PENDING_DECISIONS } from '@/mocks/handlers/bookingFixtures'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

const QUEUE_URL = '/api/venues/booking-requests'
const SUGGESTED_VENUE_NOT_ACTIVE = 'The suggested venue must be an active venue.'

/**
 * The queue, as distinct from the approved bookings under it (SCRUM-84), which can hold a
 * request with the same purpose.
 */
function queue() {
  return within(screen.getByRole('region', { name: 'Waiting for a decision' }))
}

/** The queue entry for one request, found by the purpose its heading gives it. */
async function findRequest(purpose: string) {
  return within(await queue().findByRole('article', { name: purpose }))
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

    const purposes = queue()
      .getAllByRole('heading', { level: 3 })
      .map((entry) => entry.textContent)

    // The studio is already on hold, waiting for final approval (SCRUM-75). The workshop room's
    // event moved, which flagged it, but it still waits for a decision (SCRUM-59).
    expect(purposes).toEqual(['Workshop room', 'Breakout room', 'Studio', 'Main hall'])
  })

  it('sends the approval and takes the request out of the queue', async () => {
    const requests = recordRequests()
    const { user } = renderQueue()
    const breakout = await findRequest('Breakout room')

    await user.click(breakout.getByRole('button', { name: /^Approve/ }))

    await waitFor(() =>
      expect(queue().queryByRole('article', { name: 'Breakout room' })).toBeNull(),
    )
    const decision = requests.find((sent) => sent.method === 'POST')
    expect(decision?.url).toContain(`${QUEUE_URL}/9001/decision`)
    await expect(decision?.json()).resolves.toEqual({ outcome: 'approved' })
    expect(await queue().findByRole('article', { name: 'Main hall' })).toBeInTheDocument()
  })

  it('shows the backend field error when a rejection has no reason', async () => {
    const { user } = renderQueue()
    const breakout = await findRequest('Breakout room')

    await user.click(breakout.getByRole('button', { name: /^Reject/ }))

    expect(await breakout.findByText(REJECTION_REASON_REQUIRED_MESSAGE)).toBeInTheDocument()
    expect(queue().getByRole('article', { name: 'Breakout room' })).toBeInTheDocument()
  })

  it('sends the reason with a rejection and takes the request out of the queue', async () => {
    const requests = recordRequests()
    const { user } = renderQueue()
    const breakout = await findRequest('Breakout room')

    await user.type(breakout.getByLabelText(/^Reason/), 'Closed for repairs')
    await user.click(breakout.getByRole('button', { name: /^Reject/ }))

    await waitFor(() =>
      expect(queue().queryByRole('article', { name: 'Breakout room' })).toBeNull(),
    )
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

describe('SCRUM-75 holding a venue from the venue booking decisions screen', () => {
  const HOLD_URL = `${QUEUE_URL}/9001/hold`

  /** Type an expiry into the request's hold field from scratch, and send it with the button. */
  async function sendExpiry(
    view: ReturnType<typeof renderQueue>,
    purpose: string,
    expiry: string,
    action: string,
  ) {
    const entry = await findRequest(purpose)
    const field = entry.getByLabelText(`Hold expiry for ${purpose}`)
    // The field keeps the expiry typed last, so it is cleared first.
    await view.user.clear(field)
    await view.user.type(field, expiry)
    await view.user.click(entry.getByRole('button', { name: `${action} for ${purpose}` }))
  }

  /** Hold the Breakout room until 15 Nov, 5 pm, and wait for the queue to show it on hold. */
  async function holdBreakoutRoom(view: ReturnType<typeof renderQueue>) {
    await sendExpiry(view, 'Breakout room', '2026-11-15T17:00', 'Place hold')
    const breakout = await findRequest('Breakout room')
    await breakout.findByText('Hold expiry: 15 Nov, 5:00 pm')
    return breakout
  }

  it('shows the status of each waiting request', async () => {
    renderQueue()

    const breakout = await findRequest('Breakout room')
    expect(breakout.getByText('Pending')).toBeInTheDocument()
  })

  it('sends the typed expiry in Singapore time, then shows the request on hold with it', async () => {
    const requests = recordRequests()
    const view = renderQueue()

    const breakout = await holdBreakoutRoom(view)

    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toContain(HOLD_URL)
    await expect(sent?.json()).resolves.toEqual({ expires_at: '2026-11-15T17:00:00+08:00' })
    expect(breakout.getByText('On hold')).toBeInTheDocument()
    expect(breakout.getByRole('button', { name: 'Change expiry for Breakout room' })).toBeVisible()
  })

  it("shows the backend's refusal on the card when the event has only that venue", async () => {
    const view = renderQueue()

    await sendExpiry(view, 'Main hall', '2026-11-15T17:00', 'Place hold')

    const mainHall = await findRequest('Main hall')
    expect(await mainHall.findByRole('alert')).toHaveTextContent(SINGLE_VENUE_HOLD_MESSAGE)
    expect(mainHall.getByText('Pending')).toBeInTheDocument()
  })

  it("shows the backend's message under the expiry when it is not before the event starts", async () => {
    const view = renderQueue()

    await sendExpiry(view, 'Breakout room', '2026-11-21T09:00', 'Place hold')

    const breakout = await findRequest('Breakout room')
    await waitFor(() =>
      expect(breakout.getByLabelText('Hold expiry for Breakout room')).toHaveAccessibleDescription(
        EXPIRY_NOT_BEFORE_EVENT_MESSAGE,
      ),
    )
    expect(breakout.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('moves the expiry of a request on hold', async () => {
    const requests = recordRequests()
    const view = renderQueue()
    await holdBreakoutRoom(view)

    await sendExpiry(view, 'Breakout room', '2026-11-18T12:00', 'Change expiry')

    const breakout = await findRequest('Breakout room')
    expect(await breakout.findByText('Hold expiry: 18 Nov, 12:00 pm')).toBeInTheDocument()
    const moved = requests.find((request) => request.method === 'PATCH')
    expect(moved?.url).toContain(HOLD_URL)
    await expect(moved?.json()).resolves.toEqual({ expires_at: '2026-11-18T12:00:00+08:00' })
  })

  it.each(['Approve', 'Reject'])(
    'decides a request on hold with %s, and it leaves the queue',
    async (decision) => {
      const view = renderQueue()
      const breakout = await holdBreakoutRoom(view)

      await view.user.type(breakout.getByLabelText('Reason for Breakout room'), 'Finalised')
      await view.user.click(breakout.getByRole('button', { name: `${decision} Breakout room` }))

      await waitFor(() =>
        expect(queue().queryByRole('article', { name: 'Breakout room' })).toBeNull(),
      )
    },
  )
})

describe('SCRUM-70 suggesting an alternative when rejecting', () => {
  it('sends the suggested venue and period, in Singapore time, with the rejection', async () => {
    const requests = recordRequests()
    const { user } = renderQueue()
    const breakout = await findRequest('Breakout room')

    await user.type(breakout.getByLabelText('Reason for Breakout room'), 'Closed for repairs')
    await user.type(breakout.getByLabelText('Suggested venue ID for Breakout room'), '33')
    await user.type(
      breakout.getByLabelText('Suggested start for Breakout room'),
      '2026-11-21T09:00',
    )
    await user.type(breakout.getByLabelText('Suggested end for Breakout room'), '2026-11-21T12:00')
    await user.click(breakout.getByRole('button', { name: /^Reject/ }))

    await waitFor(() =>
      expect(queue().queryByRole('article', { name: 'Breakout room' })).toBeNull(),
    )
    const decision = requests.find((sent) => sent.method === 'POST')
    await expect(decision?.json()).resolves.toEqual({
      outcome: 'rejected',
      reason: 'Closed for repairs',
      suggested_venue_id: 33,
      suggested_starts_at: '2026-11-21T09:00:00+08:00',
      suggested_ends_at: '2026-11-21T12:00:00+08:00',
    })
  })

  it("shows the backend's message under the venue when it is not active", async () => {
    const { user } = renderQueue()
    const breakout = await findRequest('Breakout room')

    await user.type(breakout.getByLabelText('Reason for Breakout room'), 'Closed')
    await user.type(breakout.getByLabelText('Suggested venue ID for Breakout room'), '34')
    await user.click(breakout.getByRole('button', { name: /^Reject/ }))

    const venueField = breakout.getByLabelText('Suggested venue ID for Breakout room')
    await waitFor(() => expect(venueField).toHaveAccessibleDescription(SUGGESTED_VENUE_NOT_ACTIVE))
    expect(breakout.queryByRole('alert')).not.toBeInTheDocument()
    expect(queue().getByRole('article', { name: 'Breakout room' })).toBeInTheDocument()
  })

  it("shows the backend's refusal under the period when it is sent with an approval", async () => {
    const { user } = renderQueue()
    const breakout = await findRequest('Breakout room')

    await user.type(
      breakout.getByLabelText('Suggested start for Breakout room'),
      '2026-11-21T09:00',
    )
    await user.type(breakout.getByLabelText('Suggested end for Breakout room'), '2026-11-21T12:00')
    await user.click(breakout.getByRole('button', { name: /^Approve/ }))

    expect(
      await breakout.findAllByText(
        'An alternative can only be suggested when rejecting a request.',
      ),
    ).toHaveLength(2)
  })
})

describe('SCRUM-92 a replacement in the decisions queue', () => {
  it('says a request replaces a booking, which approving it releases (AC7)', async () => {
    const [mainHall, breakoutRoom] = MOCK_PENDING_DECISIONS
    server.use(
      http.get(QUEUE_URL, () =>
        HttpResponse.json([{ ...breakoutRoom, replaces_request_id: 9104 }, mainHall]),
      ),
    )

    renderQueue()

    const replacement = await findRequest(breakoutRoom.purpose)
    expect(
      replacement.getByText(
        'Replaces a booking whose venue became unavailable. Approving it releases that booking.',
      ),
    ).toBeInTheDocument()
    const ordinary = await findRequest(mainHall.purpose)
    expect(ordinary.queryByText(/Replaces a booking/)).not.toBeInTheDocument()
  })
})
