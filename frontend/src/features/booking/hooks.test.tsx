import { fieldErrorsOf } from '@/lib/api'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import { MOCK_BOOKING_EVENTS, MOCK_BOOKING_VENUES } from '@/mocks/handlers/bookingFixtures'
import { recordRequests } from '@/test/recordRequests'
import { renderWithProviders } from '@/test/render'

import type { RaiseBookingRequest } from './api'
import { useBookingRequests, useRaiseBookingRequest } from './hooks'

const EVENT_REFERENCE = MOCK_BOOKING_EVENTS.approved.reference

const PAYLOAD: RaiseBookingRequest = {
  venue_id: MOCK_BOOKING_VENUES.roomy.id,
  starts_at: '2026-11-10T09:00:00+08:00',
  ends_at: '2026-11-10T12:00:00+08:00',
  purpose: 'Keynote',
}

/** Shows the event's requests and a button that raises one, so the hooks are used as a page would. */
function BookingProbe({ payload }: { payload: RaiseBookingRequest }) {
  const requests = useBookingRequests(EVENT_REFERENCE)
  const raise = useRaiseBookingRequest(EVENT_REFERENCE)
  return (
    <div>
      <p>{requests.data ? `${requests.data.length} requests` : 'loading'}</p>
      <button type="button" onClick={() => raise.mutate(payload)}>
        Raise
      </button>
      <p>{raise.error ? (fieldErrorsOf(raise.error).justification?.[0] ?? 'failed') : ''}</p>
    </div>
  )
}

const SESSION = { session: mockSessionFor(MOCK_ACCOUNTS.coordinator) }

describe('SCRUM-42 booking hooks', () => {
  it('reads the event requests from the backend', async () => {
    const requests = recordRequests()

    const view = renderWithProviders(<BookingProbe payload={PAYLOAD} />, SESSION)

    expect(await view.findByText('0 requests')).toBeInTheDocument()
    expect(requests[0]?.url).toContain(`/api/venues/events/${EVENT_REFERENCE}/booking-requests`)
  })

  it('posts the payload, then reads the requests again', async () => {
    const requests = recordRequests()
    const view = renderWithProviders(<BookingProbe payload={PAYLOAD} />, SESSION)
    await view.findByText('0 requests')

    await view.user.click(view.getByRole('button', { name: 'Raise' }))

    expect(await view.findByText('1 requests')).toBeInTheDocument()
    const post = requests.find((request) => request.method === 'POST')
    expect(await post?.json()).toEqual(PAYLOAD)
  })

  it('surfaces the backend field message when the justification is missing', async () => {
    const tiny = { ...PAYLOAD, venue_id: MOCK_BOOKING_VENUES.tiny.id }
    const view = renderWithProviders(<BookingProbe payload={tiny} />, SESSION)
    await view.findByText('0 requests')

    await view.user.click(view.getByRole('button', { name: 'Raise' }))

    expect(
      await view.findByText('A justification is required because the venue is not suitable.'),
    ).toBeInTheDocument()
  })
})
