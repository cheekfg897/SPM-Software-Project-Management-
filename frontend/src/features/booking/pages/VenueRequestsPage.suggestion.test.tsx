import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { suggestionRequestPath, venueRequestsPath } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import { MOCK_ARRANGEMENTS, MOCK_BOOKING_EVENTS } from '@/mocks/handlers/bookingFixtures'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import type { BookingRequest } from '../api'
import { typeInto } from '../test/requestForm'

/**
 * SCRUM-70: when Venue Staff reject a request with a suggested alternative, the coordinator sees
 * it beside the reason (AC3) and raises a new request from it, which they can change before
 * sending; the rejected request stays as it is (AC4). The multi-venue event's main programme was
 * rejected with the Garden Pavilion (venue 33) suggested for the next afternoon.
 */

const SESSION = { session: mockSessionFor(MOCK_ACCOUNTS.coordinator) }
const BOOKING_URL = '/api/venues/events/:reference/booking-requests'
const { rejectedMain, rejectedBreakout, bookedHall } = MOCK_ARRANGEMENTS
const EVENT = MOCK_BOOKING_EVENTS.multiVenue
const SUGGESTION_NOTE = `Starting from Venue Staff's suggestion for ${rejectedMain.purpose}.`
const LOCKED_PERIOD_HINT = 'Fixed to the booking it replaces. In Singapore time.'

function item(purpose: string): Promise<HTMLElement> {
  return screen.findByRole('listitem', { name: purpose })
}

/** Answer the event's list with these arrangements instead of the mock's own. */
function listEventAs(arrangements: BookingRequest[]) {
  server.use(http.get(BOOKING_URL, () => HttpResponse.json(arrangements)))
}

function openFromSuggestion(arrangementId: number) {
  return renderApp(suggestionRequestPath(EVENT.reference, arrangementId), SESSION)
}

async function bodiesPosted(requests: Request[]): Promise<unknown[]> {
  const posted = requests.filter((request) => request.method === 'POST')
  return Promise.all(posted.map((request) => request.json() as Promise<unknown>))
}

describe('SCRUM-70 the suggested alternative beside the rejection reason (AC3)', () => {
  it('names the suggested venue and period under the reason', async () => {
    renderApp(venueRequestsPath(EVENT.reference), SESSION)

    const rejected = await item(rejectedMain.purpose)
    expect(rejected).toHaveTextContent('Reason: Hall closed for repairs')
    expect(rejected).toHaveTextContent(
      'Venue Staff suggest instead: Venue 33 · 26 Nov, 1:00 pm – 5:00 pm',
    )
  })

  it('says the same period when only a venue was suggested', async () => {
    listEventAs([{ ...rejectedMain, suggested_starts_at: null, suggested_ends_at: null }])

    renderApp(venueRequestsPath(EVENT.reference), SESSION)

    expect(await item(rejectedMain.purpose)).toHaveTextContent(
      'Venue Staff suggest instead: Venue 33 · the same period',
    )
  })

  it('says the same venue when only a period was suggested', async () => {
    listEventAs([{ ...rejectedMain, suggested_venue_id: null }])

    renderApp(venueRequestsPath(EVENT.reference), SESSION)

    expect(await item(rejectedMain.purpose)).toHaveTextContent(
      'Venue Staff suggest instead: The same venue · 26 Nov, 1:00 pm – 5:00 pm',
    )
  })

  it('shows nothing of the kind for a rejection without a suggestion', async () => {
    renderApp(venueRequestsPath(EVENT.reference), SESSION)

    const breakout = await item(rejectedBreakout.purpose)
    expect(breakout).not.toHaveTextContent('suggest')
    expect(
      within(breakout).queryByRole('link', { name: /Raise a request from the suggestion/ }),
    ).not.toBeInTheDocument()
  })
})

describe('SCRUM-70 raising a new request from the suggestion (AC4)', () => {
  it('fills the request form from the suggestion and the rejected request', async () => {
    const view = renderApp(venueRequestsPath(EVENT.reference), SESSION)

    await view.user.click(
      await screen.findByRole('link', {
        name: `Raise a request from the suggestion for ${rejectedMain.purpose}`,
      }),
    )

    expect(await screen.findByText(SUGGESTION_NOTE, { exact: false })).toBeInTheDocument()
    expect(view.getByLabelText('Venue ID')).toHaveValue(33)
    expect(view.getByLabelText('Starts')).toHaveValue('2026-11-26T13:00')
    expect(view.getByLabelText('Ends')).toHaveValue('2026-11-26T17:00')
    expect(view.getByLabelText('Purpose')).toHaveValue(rejectedMain.purpose)
    expect(view.getByLabelText('Expected occupancy')).toHaveValue(rejectedMain.expected_occupancy)
    expect(view.getByLabelText('Starts')).not.toHaveAttribute('readonly')
  })

  it('keeps the rejected period when only a venue was suggested', async () => {
    listEventAs([{ ...rejectedMain, suggested_starts_at: null, suggested_ends_at: null }])

    const view = openFromSuggestion(rejectedMain.id)

    await screen.findByText(SUGGESTION_NOTE, { exact: false })
    expect(view.getByLabelText('Venue ID')).toHaveValue(33)
    expect(view.getByLabelText('Starts')).toHaveValue('2026-11-25T13:00')
    expect(view.getByLabelText('Ends')).toHaveValue('2026-11-25T17:00')
  })

  it('keeps the rejected venue when only a period was suggested', async () => {
    listEventAs([{ ...rejectedMain, suggested_venue_id: null }])

    const view = openFromSuggestion(rejectedMain.id)

    await screen.findByText(SUGGESTION_NOTE, { exact: false })
    expect(view.getByLabelText('Venue ID')).toHaveValue(rejectedMain.venue_id)
    expect(view.getByLabelText('Starts')).toHaveValue('2026-11-26T13:00')
  })

  it('sends what the coordinator changed as a new request, and the rejected one stays', async () => {
    const requests = recordRequests()
    const view = openFromSuggestion(rejectedMain.id)
    await screen.findByText(SUGGESTION_NOTE, { exact: false })

    await typeInto(view, 'Purpose', 'Main programme, moved')
    await view.user.click(view.getByRole('button', { name: 'Request venue' }))

    expect(await item('Main programme, moved')).toHaveTextContent('Pending')
    expect(await bodiesPosted(requests)).toEqual([
      {
        venue_id: 33,
        starts_at: '2026-11-26T13:00:00+08:00',
        ends_at: '2026-11-26T17:00:00+08:00',
        purpose: 'Main programme, moved',
        expected_occupancy: rejectedMain.expected_occupancy,
      },
    ])
    expect(await item(rejectedMain.purpose)).toHaveTextContent('Rejected')
    await waitFor(() => {
      expect(view.router.state.location.search).toBe('')
      expect(screen.queryByText(SUGGESTION_NOTE, { exact: false })).not.toBeInTheDocument()
    })
  })

  it('carries on replacing the booking a rejected replacement was for', async () => {
    const rejectedReplacement: BookingRequest = {
      ...rejectedMain,
      replaces_request_id: bookedHall.id,
      suggested_starts_at: null,
      suggested_ends_at: null,
    }
    listEventAs([rejectedReplacement])
    const requests = recordRequests()
    const view = openFromSuggestion(rejectedMain.id)
    await screen.findByText(SUGGESTION_NOTE, { exact: false })

    await view.user.click(view.getByRole('button', { name: 'Request venue' }))

    await waitFor(async () => {
      expect(await bodiesPosted(requests)).toEqual([
        expect.objectContaining({ venue_id: 33, replaces_request_id: bookedHall.id }),
      ])
    })
  })

  it('keeps a rejected replacement’s period fixed to the booking it replaces', async () => {
    // Venue Staff suggested only a venue: a replacement keeps its period (SCRUM-92 AC6).
    const rejectedReplacement: BookingRequest = {
      ...rejectedMain,
      starts_at: bookedHall.starts_at,
      ends_at: bookedHall.ends_at,
      replaces_request_id: bookedHall.id,
      suggested_starts_at: null,
      suggested_ends_at: null,
    }
    listEventAs([bookedHall, rejectedReplacement])
    const view = openFromSuggestion(rejectedMain.id)
    await screen.findByText(SUGGESTION_NOTE, { exact: false })
    const starts = view.getByLabelText('Starts')
    const ends = view.getByLabelText('Ends')

    await view.user.type(starts, '2026-11-27T09:00')

    expect([starts, ends]).toEqual([
      expect.objectContaining({ readOnly: true, value: '2026-11-26T13:00' }),
      expect.objectContaining({ readOnly: true, value: '2026-11-26T17:00' }),
    ])
    expect(starts).toHaveAccessibleDescription(LOCKED_PERIOD_HINT)
  })

  it('raises an ordinary request once the coordinator stops using the suggestion', async () => {
    const view = openFromSuggestion(rejectedMain.id)
    await screen.findByText(SUGGESTION_NOTE, { exact: false })

    await view.user.click(screen.getByRole('button', { name: 'Stop using the suggestion' }))

    expect(screen.queryByText(SUGGESTION_NOTE, { exact: false })).not.toBeInTheDocument()
    expect(view.router.state.location.search).toBe('')
    expect(view.getByLabelText('Venue ID')).toHaveValue(null)
  })

  it('starts an ordinary request when the list does not hold the request named', async () => {
    const view = openFromSuggestion(777)

    await item(rejectedMain.purpose)
    expect(screen.queryByText(/Starting from Venue Staff's suggestion/)).not.toBeInTheDocument()
    expect(view.getByLabelText('Venue ID')).toHaveValue(null)
  })
})
