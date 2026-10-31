import { screen, waitFor, within } from '@testing-library/react'
import { http } from 'msw'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import { MOCK_ARRANGEMENTS, MOCK_BOOKING_EVENTS } from '@/mocks/handlers/bookingFixtures'
import { errorResponse } from '@/mocks/responses'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

/**
 * SCRUM-111: the coordinator cancels one approved booking, with a reason, from the event's Venue
 * requests page. The booking's arrangement becomes Cancelled and the event's other ones stay as
 * they were (AC1, AC2); a refusal shows in the backend's words (AC4).
 */

const SESSION = { session: mockSessionFor(MOCK_ACCOUNTS.coordinator) }
const BOOKED_EVENT = MOCK_BOOKING_EVENTS.booked
const { bookedHall, bookedSideRoom } = MOCK_ARRANGEMENTS
const REASON = 'The talks moved to the side room.'
const CANCEL_PATH = `/api/venues/events/${BOOKED_EVENT.reference}/booking-requests/${bookedHall.id}/cancel`

type AppView = ReturnType<typeof renderApp>

function item(purpose: string): Promise<HTMLElement> {
  return screen.findByRole('listitem', { name: purpose })
}

function openBookedEvent(): AppView {
  return renderApp(`/events/${BOOKED_EVENT.reference}/venue-requests`, SESSION)
}

/** Open the cancel form for the booked event's approved hall. */
async function openCancelForm(view: AppView): Promise<HTMLElement> {
  await view.user.click(
    await screen.findByRole('button', { name: `Cancel booking ${bookedHall.purpose}` }),
  )
  return screen.getByRole('form', { name: `Cancel booking ${bookedHall.purpose}` })
}

function postsTo(requests: Request[]): string[] {
  return requests
    .filter((request) => request.method === 'POST')
    .map((request) => new URL(request.url).pathname)
}

async function bodiesPosted(requests: Request[]): Promise<unknown[]> {
  const posted = requests.filter((request) => request.method === 'POST')
  return Promise.all(posted.map((request) => request.json() as Promise<unknown>))
}

describe('SCRUM-111 cancelling an approved booking on the venue requests page', () => {
  it('offers to cancel an approved booking, and not an arrangement that is not approved', async () => {
    openBookedEvent()

    const hall = await item(bookedHall.purpose)
    expect(
      within(hall).getByRole('button', { name: `Cancel booking ${bookedHall.purpose}` }),
    ).toBeEnabled()
    const sideRoom = await item(bookedSideRoom.purpose)
    expect(sideRoom).toHaveTextContent('Rejected')
    expect(within(sideRoom).queryByRole('button', { name: /^Cancel booking/ })).toBeNull()
  })

  it('asks for a reason first, and sends nothing until the coordinator confirms', async () => {
    const requests = recordRequests()
    const view = openBookedEvent()

    const form = await openCancelForm(view)

    expect(within(form).getByLabelText('Reason for cancelling')).toHaveValue('')
    expect(form).toHaveTextContent(
      'The venue is freed for this period and Venue Staff are told. The event’s other venues stay as they are.',
    )
    expect(postsTo(requests)).toEqual([])
  })

  it('sends the reason, then lists the booking as Cancelled with nothing left to do on it', async () => {
    const requests = recordRequests()
    const view = openBookedEvent()
    const form = await openCancelForm(view)
    await view.user.type(within(form).getByLabelText('Reason for cancelling'), REASON)

    await view.user.click(within(form).getByRole('button', { name: 'Cancel booking' }))

    await waitFor(async () => expect(await item(bookedHall.purpose)).toHaveTextContent('Cancelled'))
    const hall = await item(bookedHall.purpose)
    expect(within(hall).queryByRole('button')).toBeNull()
    expect(screen.queryByRole('form', { name: /^Cancel booking/ })).toBeNull()
    expect(await item(bookedSideRoom.purpose)).toHaveTextContent('Rejected')
    expect(postsTo(requests)).toEqual([CANCEL_PATH])
    expect(await bodiesPosted(requests)).toEqual([{ reason: REASON }])
  })

  it('sends no reason when none is typed, and shows the backend’s message under the box', async () => {
    const requests = recordRequests()
    const view = openBookedEvent()
    const form = await openCancelForm(view)

    await view.user.click(within(form).getByRole('button', { name: 'Cancel booking' }))

    expect(await within(form).findByLabelText('Reason for cancelling')).toHaveAccessibleDescription(
      'A reason is required to cancel a booking.',
    )
    expect(within(form).getByRole('alert')).toHaveTextContent('Invalid request.')
    expect(await bodiesPosted(requests)).toEqual([{}])
    expect(await item(bookedHall.purpose)).toHaveTextContent('Approved')
  })

  it('shows the backend’s refusal in its own words, and reads the list again', async () => {
    const message =
      'Only an approved event or one in Safety Review can have a venue booking cancelled; this one is confirmed.'
    server.use(
      http.post('/api/venues/events/:reference/booking-requests/:id/cancel', () =>
        errorResponse(409, 'conflict', message),
      ),
    )
    const view = openBookedEvent()
    const form = await openCancelForm(view)
    await view.user.type(within(form).getByLabelText('Reason for cancelling'), REASON)
    const requests = recordRequests()

    await view.user.click(within(form).getByRole('button', { name: 'Cancel booking' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent(message)
    await waitFor(() =>
      expect(requests.filter((request) => request.method === 'GET')).not.toEqual([]),
    )
  })

  it('keeps the booking when the coordinator thinks better of it', async () => {
    const requests = recordRequests()
    const view = openBookedEvent()
    const form = await openCancelForm(view)
    await view.user.type(within(form).getByLabelText('Reason for cancelling'), REASON)

    await view.user.click(within(form).getByRole('button', { name: 'Keep it' }))

    expect(screen.queryByRole('form', { name: /^Cancel booking/ })).toBeNull()
    expect(
      screen.getByRole('button', { name: `Cancel booking ${bookedHall.purpose}` }),
    ).toBeEnabled()
    expect(postsTo(requests)).toEqual([])
  })

  it('shows a cancelled arrangement as Cancelled, with nothing to do on it', async () => {
    server.use(
      http.get('/api/venues/events/:reference/booking-requests', () =>
        Response.json([{ ...bookedHall, status: 'cancelled', needs_alternative_venue: false }]),
      ),
    )
    openBookedEvent()

    const hall = await item(bookedHall.purpose)
    expect(hall).toHaveTextContent('Cancelled')
    expect(within(hall).queryByRole('button')).toBeNull()
  })
})
