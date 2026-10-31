import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import {
  MOCK_ARRANGEMENTS,
  MOCK_BOOKING_EVENTS,
  MOCK_BOOKING_VENUES,
} from '@/mocks/handlers/bookingFixtures'
import { errorResponse } from '@/mocks/responses'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import { fillRequest, typeInto } from '../test/requestForm'

/**
 * SCRUM-93: the coordinator changes, withdraws or cancels an event's venue arrangements from
 * its Venue requests page. The backend decides which it allows; the page shows its answer.
 */

const SESSION = { session: mockSessionFor(MOCK_ACCOUNTS.coordinator) }
const {
  rejectedMain,
  rejectedBreakout,
  withdrawnOverflow,
  bookedHall,
  bookedSideRoom,
  releasedHall,
  expiredGallery,
  heldStudio,
} = MOCK_ARRANGEMENTS
/** The backend's refusal to withdraw an approved arrangement (WITHDRAW_NOT_ALLOWED_MESSAGE). */
const APPROVED_WITHDRAW_REFUSAL =
  'Only a pending, conflicting, held, rejected or expired arrangement can be withdrawn; this one is approved.'

type AppView = ReturnType<typeof renderApp>

function pathOf(reference: string): string {
  return `/events/${reference}/venue-requests`
}

function openEvent(reference: string): AppView {
  return renderApp(pathOf(reference), SESSION)
}

function item(purpose: string): Promise<HTMLElement> {
  return screen.findByRole('listitem', { name: purpose })
}

/** Raise a request on the approved event through its form, and wait for it to be listed. */
async function raiseThroughForm(view: AppView, purpose: string, venueId: number) {
  await fillRequest(view, venueId)
  await typeInto(view, 'Purpose', purpose)
  await view.user.click(view.getByRole('button', { name: 'Request venue' }))
  await item(purpose)
  await waitFor(() => expect(view.getByLabelText('Purpose')).toHaveValue(''))
}

/** The approved event with one pending request on the roomy venue, called "Keynote". */
async function eventWithKeynote(): Promise<AppView> {
  const view = openEvent(MOCK_BOOKING_EVENTS.approved.reference)
  await raiseThroughForm(view, 'Keynote', MOCK_BOOKING_VENUES.roomy.id)
  return view
}

async function openChangeForm(view: AppView, purpose: string): Promise<HTMLElement> {
  await view.user.click(await screen.findByRole('button', { name: `Change ${purpose}` }))
  return screen.getByRole('form', { name: `Change ${purpose}` })
}

async function bodiesSent(requests: Request[], method: string): Promise<unknown[]> {
  const sent = requests.filter((request) => request.method === method)
  return Promise.all(sent.map((request) => request.json() as Promise<unknown>))
}

function pathsPosted(requests: Request[]): string[] {
  return requests
    .filter((request) => request.method === 'POST')
    .map((request) => new URL(request.url).pathname)
}

describe('SCRUM-93 venue arrangements on the venue requests page', () => {
  it('shows each arrangement with its status, and offers nothing for a withdrawn one', async () => {
    openEvent(MOCK_BOOKING_EVENTS.multiVenue.reference)

    const withdrawn = await item(withdrawnOverflow.purpose)
    expect(withdrawn).toHaveTextContent('Withdrawn')
    expect(within(withdrawn).queryByRole('button')).not.toBeInTheDocument()
    const rejected = await item(rejectedMain.purpose)
    expect(rejected).toHaveTextContent('Rejected')
    expect(rejected).toHaveTextContent('Reason: Hall closed for repairs')
    expect(
      within(rejected).getByRole('button', { name: `Withdraw ${rejectedMain.purpose}` }),
    ).toBeEnabled()
    expect(
      within(rejected).getByRole('button', { name: `Change ${rejectedMain.purpose}` }),
    ).toBeEnabled()
  })

  it('offers nothing for a released arrangement, which a replacement took over, but does for an expired one', async () => {
    openEvent(MOCK_BOOKING_EVENTS.replaced.reference)

    const released = await item(releasedHall.purpose)
    expect(released).toHaveTextContent('Released')
    expect(within(released).queryByRole('button')).not.toBeInTheDocument()
    const expired = await item(expiredGallery.purpose)
    expect(expired).toHaveTextContent('Expired')
    expect(
      within(expired).getByRole('button', { name: `Withdraw ${expiredGallery.purpose}` }),
    ).toBeEnabled()
  })

  it('withdraws one arrangement and leaves the event’s other ones as they were', async () => {
    const requests = recordRequests()
    const view = openEvent(MOCK_BOOKING_EVENTS.multiVenue.reference)

    await view.user.click(
      await screen.findByRole('button', { name: `Withdraw ${rejectedBreakout.purpose}` }),
    )

    await waitFor(async () =>
      expect(await item(rejectedBreakout.purpose)).toHaveTextContent('Withdrawn'),
    )
    expect(
      within(await item(rejectedBreakout.purpose)).queryByRole('button'),
    ).not.toBeInTheDocument()
    expect(await item(rejectedMain.purpose)).toHaveTextContent('Rejected')
    expect(pathsPosted(requests)).toEqual([
      `/api/venues/events/${MOCK_BOOKING_EVENTS.multiVenue.reference}/booking-requests/${rejectedBreakout.id}/withdraw`,
    ])
  })

  it('withdraws an arrangement on hold, so its hold and expiry go with it', async () => {
    const requests = recordRequests()
    const view = openEvent(MOCK_BOOKING_EVENTS.held.reference)
    expect(await item(heldStudio.purpose)).toHaveTextContent('Hold expiry')

    await view.user.click(
      await screen.findByRole('button', { name: `Withdraw ${heldStudio.purpose}` }),
    )

    await waitFor(async () => expect(await item(heldStudio.purpose)).toHaveTextContent('Withdrawn'))
    const withdrawn = await item(heldStudio.purpose)
    expect(withdrawn).not.toHaveTextContent('Hold expiry')
    expect(within(withdrawn).queryByRole('button')).not.toBeInTheDocument()
    expect(pathsPosted(requests)).toEqual([
      `/api/venues/events/${MOCK_BOOKING_EVENTS.held.reference}/booking-requests/${heldStudio.id}/withdraw`,
    ])
  })

  it('says which arrangement needs an alternative venue, as the backend flags it', async () => {
    openEvent(MOCK_BOOKING_EVENTS.booked.reference)

    expect(await item(bookedHall.purpose)).toHaveTextContent('Needs an alternative venue')
    expect(await item(bookedSideRoom.purpose)).not.toHaveTextContent('alternative venue')
  })

  it('shows the backend’s refusal in the arrangement it was about', async () => {
    const view = openEvent(MOCK_BOOKING_EVENTS.booked.reference)

    await view.user.click(
      await screen.findByRole('button', { name: `Withdraw ${bookedHall.purpose}` }),
    )

    const hall = await item(bookedHall.purpose)
    expect(await within(hall).findByRole('alert')).toHaveTextContent(APPROVED_WITHDRAW_REFUSAL)
    expect(hall).toHaveTextContent('Approved')
    expect(within(await item(bookedSideRoom.purpose)).queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows whatever refusal the backend sends, such as one naming the event’s status', async () => {
    // The mock's confirmed event has no arrangements to offer a Withdraw on, so the route is
    // made to answer as the backend does for one (SCRUM-93 AC10).
    const message =
      'Only an approved event or one in Safety Review can have its venue arrangements withdrawn, changed or cancelled; this one is confirmed.'
    server.use(
      http.post('/api/venues/events/:reference/booking-requests/:id/withdraw', () =>
        errorResponse(409, 'conflict', message),
      ),
    )
    const view = openEvent(MOCK_BOOKING_EVENTS.multiVenue.reference)

    await view.user.click(
      await screen.findByRole('button', { name: `Withdraw ${rejectedMain.purpose}` }),
    )

    expect(await within(await item(rejectedMain.purpose)).findByRole('alert')).toHaveTextContent(
      message,
    )
  })

  it('opens the change form holding the arrangement’s current values', async () => {
    const view = await eventWithKeynote()
    await view.user.click(view.getByRole('button', { name: 'Change Keynote' }))
    const form = screen.getByRole('form', { name: 'Change Keynote' })

    expect(within(form).getByLabelText('Purpose')).toHaveValue('Keynote')
    expect(within(form).getByLabelText('Expected occupancy')).toHaveValue(
      MOCK_BOOKING_EVENTS.approved.expected_attendance,
    )
    expect(within(form).getByLabelText('Required layout')).toHaveValue('')
    expect(within(form).getByLabelText('Justification')).toHaveValue('')
  })

  it('opens the change form with the layout and justification an arrangement already has', async () => {
    server.use(
      http.get('/api/venues/events/:reference/booking-requests', () =>
        HttpResponse.json([
          { ...rejectedBreakout, required_layout: 'boardroom', justification: 'Only room free' },
        ]),
      ),
    )
    const view = openEvent(MOCK_BOOKING_EVENTS.multiVenue.reference)

    const form = await openChangeForm(view, rejectedBreakout.purpose)

    expect(within(form).getByLabelText('Required layout')).toHaveValue('boardroom')
    expect(within(form).getByLabelText('Justification')).toHaveValue('Only room free')
  })

  it('sends the changed values, then lists the arrangement as the backend now has it', async () => {
    const requests = recordRequests()
    const view = await eventWithKeynote()
    const form = await openChangeForm(view, 'Keynote')
    await view.user.clear(within(form).getByLabelText('Purpose'))
    await view.user.type(within(form).getByLabelText('Purpose'), 'Opening plenary')
    await view.user.clear(within(form).getByLabelText('Expected occupancy'))
    await view.user.type(within(form).getByLabelText('Expected occupancy'), '120')
    await view.user.selectOptions(within(form).getByLabelText('Required layout'), 'Theatre')
    await view.user.type(within(form).getByLabelText('Justification'), 'Sponsors asked')

    await view.user.click(within(form).getByRole('button', { name: 'Save changes' }))

    const changed = await item('Opening plenary')
    expect(changed).toHaveTextContent('120 guests · Theatre')
    expect(screen.queryByRole('form', { name: /^Change/ })).not.toBeInTheDocument()
    expect(await bodiesSent(requests, 'PATCH')).toEqual([
      {
        purpose: 'Opening plenary',
        expected_occupancy: 120,
        required_layout: 'theatre',
        justification: 'Sponsors asked',
      },
    ])
  })

  it('clears the layout by sending null, and leaves out an empty occupancy and justification', async () => {
    const requests = recordRequests()
    const view = openEvent(MOCK_BOOKING_EVENTS.approved.reference)
    await fillRequest(view, MOCK_BOOKING_VENUES.roomy.id)
    await view.user.selectOptions(view.getByLabelText('Required layout'), 'Banquet')
    await view.user.click(view.getByRole('button', { name: 'Request venue' }))
    const form = await openChangeForm(view, 'Keynote')
    await view.user.clear(within(form).getByLabelText('Expected occupancy'))
    await view.user.selectOptions(within(form).getByLabelText('Required layout'), 'No preference')

    await view.user.click(within(form).getByRole('button', { name: 'Save changes' }))

    await waitFor(async () => expect(await item('Keynote')).toHaveTextContent('No layout set'))
    expect(await bodiesSent(requests, 'PATCH')).toEqual([
      { purpose: 'Keynote', required_layout: null },
    ])
  })

  it('shows the backend’s message against the justification when the venue no longer suits', async () => {
    const view = openEvent(MOCK_BOOKING_EVENTS.approved.reference)
    await fillRequest(view, MOCK_BOOKING_VENUES.tiny.id)
    await typeInto(view, 'Expected occupancy', '5')
    await view.user.click(view.getByRole('button', { name: 'Request venue' }))
    const form = await openChangeForm(view, 'Keynote')
    await view.user.clear(within(form).getByLabelText('Expected occupancy'))
    await view.user.type(within(form).getByLabelText('Expected occupancy'), '50')

    await view.user.click(within(form).getByRole('button', { name: 'Save changes' }))

    expect(await within(form).findByLabelText('Justification')).toHaveAccessibleDescription(
      'A justification is required because the venue is not suitable.',
    )
    expect(within(form).getByRole('alert')).toHaveTextContent('Invalid request.')
    expect(await item('Keynote')).toHaveTextContent('5 guests')
  })

  it('shows the backend’s refusal to change a decided arrangement, in its form', async () => {
    const view = openEvent(MOCK_BOOKING_EVENTS.booked.reference)
    const form = await openChangeForm(view, bookedHall.purpose)

    await view.user.click(within(form).getByRole('button', { name: 'Save changes' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent(
      'Only a pending arrangement can be changed; this one is approved.',
    )
  })

  it('closes the change form without sending anything', async () => {
    const requests = recordRequests()
    const view = openEvent(MOCK_BOOKING_EVENTS.multiVenue.reference)
    const form = await openChangeForm(view, rejectedMain.purpose)

    await view.user.click(within(form).getByRole('button', { name: 'Close' }))

    expect(screen.queryByRole('form', { name: /^Change/ })).not.toBeInTheDocument()
    expect(requests.filter((request) => request.method !== 'GET')).toEqual([])
  })

  it('asks before cancelling all, and withdraws every arrangement once confirmed', async () => {
    const view = await eventWithKeynote()
    await typeInto(view, 'Justification', 'Standing room')
    await raiseThroughForm(view, 'Workshop', MOCK_BOOKING_VENUES.tiny.id)
    const requests = recordRequests()

    await view.user.click(view.getByRole('button', { name: 'Cancel all venue requests' }))
    expect(pathsPosted(requests)).toEqual([])
    await view.user.click(view.getByRole('button', { name: 'Withdraw them all' }))

    await waitFor(async () => expect(await item('Keynote')).toHaveTextContent('Withdrawn'))
    expect(await item('Workshop')).toHaveTextContent('Withdrawn')
    expect(pathsPosted(requests)).toEqual([
      `/api/venues/events/${MOCK_BOOKING_EVENTS.approved.reference}/booking-requests/cancel-all`,
    ])
    expect(screen.queryByRole('button', { name: 'Withdraw them all' })).not.toBeInTheDocument()
  })

  it('keeps every arrangement when the coordinator thinks better of cancelling all', async () => {
    const requests = recordRequests()
    const view = openEvent(MOCK_BOOKING_EVENTS.multiVenue.reference)
    await item(rejectedMain.purpose)

    await view.user.click(view.getByRole('button', { name: 'Cancel all venue requests' }))
    await view.user.click(view.getByRole('button', { name: 'Keep them' }))

    expect(screen.queryByRole('button', { name: 'Withdraw them all' })).not.toBeInTheDocument()
    expect(view.getByRole('button', { name: 'Cancel all venue requests' })).toBeEnabled()
    expect(pathsPosted(requests)).toEqual([])
  })

  it('shows the backend’s refusal to cancel all, and every arrangement stays as it was', async () => {
    const view = openEvent(MOCK_BOOKING_EVENTS.booked.reference)
    await item(bookedHall.purpose)

    await view.user.click(view.getByRole('button', { name: 'Cancel all venue requests' }))
    await view.user.click(view.getByRole('button', { name: 'Withdraw them all' }))

    const section = screen.getByRole('region', { name: 'Cancel all venue requests' })
    expect(await within(section).findByRole('alert')).toHaveTextContent(APPROVED_WITHDRAW_REFUSAL)
    expect(await item(bookedSideRoom.purpose)).toHaveTextContent('Rejected')
  })

  it('forgets a refusal once the coordinator keeps the arrangements, so asking again starts clean', async () => {
    const view = openEvent(MOCK_BOOKING_EVENTS.booked.reference)
    await item(bookedHall.purpose)
    await view.user.click(view.getByRole('button', { name: 'Cancel all venue requests' }))
    await view.user.click(view.getByRole('button', { name: 'Withdraw them all' }))
    const section = screen.getByRole('region', { name: 'Cancel all venue requests' })
    await within(section).findByRole('alert')

    await view.user.click(view.getByRole('button', { name: 'Keep them' }))
    await view.user.click(view.getByRole('button', { name: 'Cancel all venue requests' }))

    expect(view.getByRole('button', { name: 'Withdraw them all' })).toBeEnabled()
    expect(
      within(screen.getByRole('region', { name: 'Cancel all venue requests' })).queryByRole(
        'alert',
      ),
    ).not.toBeInTheDocument()
  })

  it('offers no cancel-all while the event has no venue requests', async () => {
    openEvent(MOCK_BOOKING_EVENTS.approved.reference)

    await screen.findByText('No venue requests yet.')
    expect(
      screen.queryByRole('button', { name: 'Cancel all venue requests' }),
    ).not.toBeInTheDocument()
  })
})
