import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { replacementRequestPath, ROUTES, venueRequestsPath } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/handlers/auth'
import {
  MOCK_ARRANGEMENTS,
  MOCK_BOOKING_EVENTS,
  MOCK_BOOKING_VENUES,
} from '@/mocks/handlers/bookingFixtures'
import { errorResponse, validationError } from '@/mocks/responses'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import type { BookingRequest, ReassessmentFlag } from '../api'
import { fillRequest, typeInto } from '../test/requestForm'

/**
 * SCRUM-92: an arrangement whose venue became unavailable is flagged by the backend. The
 * coordinator sees why under it, with the original booking still shown, finds another venue
 * for its period and raises a replacement linked to it.
 */

const SESSION = { session: mockSessionFor(MOCK_ACCOUNTS.coordinator) }
const BOOKING_URL = '/api/venues/events/:reference/booking-requests'
const { bookedHall, bookedSideRoom, reviewedAuditorium } = MOCK_ARRANGEMENTS
const BOOKED_EVENT = MOCK_BOOKING_EVENTS.booked
const CAUSES_LABEL = 'Why its venue is unavailable'

function openEvent(reference: string) {
  return renderApp(venueRequestsPath(reference), SESSION)
}

/** Answer the booked event's list with these arrangements instead of the mock's own. */
function listBookedEventAs(arrangements: BookingRequest[]) {
  server.use(http.get(BOOKING_URL, () => HttpResponse.json(arrangements)))
}

function item(purpose: string): Promise<HTMLElement> {
  return screen.findByRole('listitem', { name: purpose })
}

/** Each entry of the list named `listName` under the arrangement, as its text. */
async function listedUnder(purpose: string, listName: string): Promise<string[]> {
  const list = within(await item(purpose)).getByRole('list', { name: listName })
  return within(list)
    .getAllByRole('listitem')
    .map((entry) => entry.textContent)
}

/** Each cause listed under the arrangement, as its text. */
function causesUnder(purpose: string): Promise<string[]> {
  return listedUnder(purpose, CAUSES_LABEL)
}

describe('SCRUM-92 why an arrangement needs an alternative venue', () => {
  it('names the block’s category, its note and its period in business time (AC1, AC2)', async () => {
    openEvent(BOOKED_EVENT.reference)

    expect(await causesUnder(bookedHall.purpose)).toEqual([
      'Maintenance: Roof repairs. Unavailable from 26 Nov, 8:00 am to 26 Nov, 6:00 pm.',
    ])
  })

  it('says a deactivated venue is unavailable until it is reactivated (AC9)', async () => {
    openEvent(MOCK_BOOKING_EVENTS.inSafetyReview.reference)

    expect(await causesUnder(reviewedAuditorium.purpose)).toEqual([
      'Renovation: Closed for refit. Unavailable from 1 Nov, 12:00 pm until the venue is reactivated.',
    ])
  })

  it('lists every block that flagged it, in the backend’s order', async () => {
    listBookedEventAs([
      {
        ...bookedHall,
        unavailability: [
          ...bookedHall.unavailability,
          {
            category: 'equipment_failure',
            reason: 'Lift broken',
            starts_at: '2026-11-26T12:00:00+08:00',
            ends_at: '2026-11-27T09:00:00+08:00',
          },
        ],
      },
    ])

    openEvent(BOOKED_EVENT.reference)

    expect(await causesUnder(bookedHall.purpose)).toEqual([
      'Maintenance: Roof repairs. Unavailable from 26 Nov, 8:00 am to 26 Nov, 6:00 pm.',
      'Equipment failure: Lift broken. Unavailable from 26 Nov, 12:00 pm to 27 Nov, 9:00 am.',
    ])
  })

  it('shows why a flagged On Hold arrangement needs another venue, and offers to find one (AC1)', async () => {
    const { heldStudio } = MOCK_ARRANGEMENTS
    listBookedEventAs([
      {
        ...heldStudio,
        needs_alternative_venue: true,
        unavailability: bookedHall.unavailability,
      },
    ])

    openEvent(BOOKED_EVENT.reference)

    const studio = await item(heldStudio.purpose)
    expect(studio).toHaveTextContent('On hold')
    expect(await causesUnder(heldStudio.purpose)).toEqual([
      'Maintenance: Roof repairs. Unavailable from 26 Nov, 8:00 am to 26 Nov, 6:00 pm.',
    ])
    expect(
      within(studio).getByRole('link', { name: `Find another venue for ${heldStudio.purpose}` }),
    ).toBeInTheDocument()
  })

  it('keeps the original booking and its details on show (AC4)', async () => {
    openEvent(BOOKED_EVENT.reference)

    const hall = await item(bookedHall.purpose)
    expect(hall).toHaveTextContent('Approved')
    expect(hall).toHaveTextContent('Venue 1 · 26 Nov, 1:00 pm – 5:00 pm')
    expect(hall).toHaveTextContent('Reason: Booked')
  })

  it('shows nothing of the kind for an arrangement that is not flagged', async () => {
    openEvent(BOOKED_EVENT.reference)

    const sideRoom = await item(bookedSideRoom.purpose)
    expect(sideRoom).not.toHaveTextContent('alternative venue')
    expect(within(sideRoom).queryByRole('list', { name: CAUSES_LABEL })).not.toBeInTheDocument()
  })

  it('drops the flag once the backend clears it, and the original booking stands (AC8)', async () => {
    listBookedEventAs([{ ...bookedHall, needs_alternative_venue: false, unavailability: [] }])

    openEvent(BOOKED_EVENT.reference)

    const hall = await item(bookedHall.purpose)
    expect(hall).toHaveTextContent('Approved')
    expect(hall).not.toHaveTextContent('alternative venue')
  })

  it('shows a released arrangement as Released, with no flag, though the backend keeps why (AC7)', async () => {
    listBookedEventAs([{ ...bookedHall, status: 'released', needs_alternative_venue: false }])

    openEvent(BOOKED_EVENT.reference)

    const hall = await item(bookedHall.purpose)
    expect(hall).toHaveTextContent('Released')
    expect(hall).not.toHaveTextContent('alternative venue')
    expect(within(hall).queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('SCRUM-92 raising a replacement for a flagged arrangement (AC6)', () => {
  const TINY_VENUE = MOCK_BOOKING_VENUES.tiny
  const REPLACEMENT_NOTE = `Replacing ${bookedHall.purpose}`

  /** The event's page, raising a replacement for `arrangementId` at the tiny venue. */
  function openReplacing(reference: string, arrangementId: number) {
    return renderApp(replacementRequestPath(reference, arrangementId, TINY_VENUE.id), SESSION)
  }

  function requestButton(view: ReturnType<typeof renderApp>) {
    return view.getByRole('button', { name: 'Request venue' })
  }

  async function bodiesPosted(requests: Request[]): Promise<unknown[]> {
    const posted = requests.filter((request) => request.method === 'POST')
    return Promise.all(posted.map((request) => request.json() as Promise<unknown>))
  }

  it('offers to find another venue for the flagged arrangement, set to its period', async () => {
    const view = openEvent(BOOKED_EVENT.reference)

    await view.user.click(
      await screen.findByRole('link', { name: `Find another venue for ${bookedHall.purpose}` }),
    )

    expect(view.router.state.location.pathname).toBe(ROUTES.VENUE_SEARCH)
    const params = new URLSearchParams(view.router.state.location.search)
    expect([
      params.get('replaces'),
      params.get('instead_of'),
      params.get('date'),
      params.get('start'),
    ]).toEqual([String(bookedHall.id), String(bookedHall.venue_id), '2026-11-26', '13:00'])
  })

  it('offers no venue search for an arrangement that is not flagged', async () => {
    openEvent(BOOKED_EVENT.reference)

    const sideRoom = await item(bookedSideRoom.purpose)
    expect(within(sideRoom).queryByRole('link')).not.toBeInTheDocument()
  })

  it('fills the request form from the flagged arrangement and the venue chosen', async () => {
    const view = openReplacing(BOOKED_EVENT.reference, bookedHall.id)

    expect(await screen.findByText(REPLACEMENT_NOTE, { exact: false })).toBeInTheDocument()
    expect(view.getByLabelText('Venue ID')).toHaveValue(TINY_VENUE.id)
    expect(view.getByLabelText('Starts')).toHaveValue('2026-11-26T13:00')
    expect(view.getByLabelText('Ends')).toHaveValue('2026-11-26T17:00')
    expect(view.getByLabelText('Purpose')).toHaveValue(bookedHall.purpose)
    expect(view.getByLabelText('Expected occupancy')).toHaveValue(bookedHall.expected_occupancy)
    expect(view.getByLabelText('Required layout')).toHaveValue('')
  })

  it('sends the replacement linked to the flagged arrangement, then lists it as replacing it', async () => {
    const requests = recordRequests()
    const view = openReplacing(BOOKED_EVENT.reference, bookedHall.id)
    await screen.findByText(REPLACEMENT_NOTE, { exact: false })

    await typeInto(view, 'Purpose', 'Main hall, moved')
    await view.user.click(requestButton(view))

    const replacement = await item('Main hall, moved')
    expect(replacement).toHaveTextContent('Pending')
    expect(replacement).toHaveTextContent(`Replaces ${bookedHall.purpose}`)
    expect(await bodiesPosted(requests)).toEqual([
      {
        venue_id: TINY_VENUE.id,
        starts_at: bookedHall.starts_at,
        ends_at: bookedHall.ends_at,
        purpose: 'Main hall, moved',
        expected_occupancy: bookedHall.expected_occupancy,
        replaces_request_id: bookedHall.id,
      },
    ])
    // The form stops replacing once the request is saved, after the list is read again.
    await waitFor(() => {
      expect(view.router.state.location.search).toBe('')
      expect(screen.queryByText(REPLACEMENT_NOTE, { exact: false })).not.toBeInTheDocument()
    })
    expect(view.getByLabelText('Purpose')).toHaveValue('')
  })

  it('shows the backend’s refusal of an arrangement that needs no alternative venue', async () => {
    const view = openReplacing(BOOKED_EVENT.reference, bookedSideRoom.id)
    await screen.findByText(`Replacing ${bookedSideRoom.purpose}`, { exact: false })

    await view.user.click(requestButton(view))

    expect(
      await screen.findByText('This venue arrangement does not need an alternative venue.'),
    ).toBeInTheDocument()
  })

  it('shows the backend’s refusal once the event can no longer replace a venue', async () => {
    const view = openReplacing(MOCK_BOOKING_EVENTS.confirmed.reference, bookedHall.id)
    // The confirmed event has no such arrangement, so the form names it by its id.
    await screen.findByText(`Replacing arrangement ${bookedHall.id}`, { exact: false })

    await fillRequest(view, TINY_VENUE.id)
    await view.user.click(requestButton(view))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Only an approved event or one in Safety Review can replace a venue; this one is confirmed.',
    )
  })

  it.each([
    [
      'its 400 on the arrangement replaced, beside the replacement',
      () => validationError({ replaces_request_id: ['Arrangement 9104 was replaced on 12 Nov.'] }),
      'Arrangement 9104 was replaced on 12 Nov.',
    ],
    [
      'its 409 on the event',
      () => errorResponse(409, 'conflict', 'The event was cancelled at 3:12 pm.'),
      'The event was cancelled at 3:12 pm.',
    ],
  ])('shows the backend’s own words for %s', async (_case, respond, message) => {
    server.use(http.post(BOOKING_URL, respond))
    const view = openReplacing(BOOKED_EVENT.reference, bookedHall.id)
    await screen.findByText(REPLACEMENT_NOTE, { exact: false })

    await view.user.click(requestButton(view))

    expect(await screen.findByText(message)).toBeInTheDocument()
  })

  it('raises an ordinary request once the coordinator stops replacing', async () => {
    const requests = recordRequests()
    const view = openReplacing(MOCK_BOOKING_EVENTS.approved.reference, bookedHall.id)
    await screen.findByText(`Replacing arrangement ${bookedHall.id}`, { exact: false })

    await view.user.click(screen.getByRole('button', { name: 'Stop replacing' }))

    expect(screen.queryByText(/Replacing arrangement/)).not.toBeInTheDocument()
    expect(view.router.state.location.search).toBe('')
    await fillRequest(view, TINY_VENUE.id)
    await typeInto(view, 'Expected occupancy', '5')
    await view.user.click(requestButton(view))
    await item('Keynote')
    const [body] = await bodiesPosted(requests)
    expect(body).not.toHaveProperty('replaces_request_id')
  })

  it('names a replacement’s original by its id when the list does not hold it', async () => {
    listBookedEventAs([{ ...bookedSideRoom, purpose: 'Stand-in hall', replaces_request_id: 777 }])

    openEvent(BOOKED_EVENT.reference)

    expect(await item('Stand-in hall')).toHaveTextContent('Replaces arrangement 777')
  })
})

/**
 * SCRUM-33 AC6 (ADR-0094): a significant change to the event flags the arrangements it affects.
 * Until Venue Staff can reconfirm a booking (SCRUM-59), a replacement is the way to clear one,
 * so the coordinator sees why and is offered the same venue search.
 */
describe('SCRUM-33 an arrangement flagged after a change to the event', () => {
  const CHANGE_REASONS_LABEL = 'Why a change to the event flagged it'
  const TIMING_CHANGED: ReassessmentFlag = {
    kind: 'requires_reconfirmation',
    reason: "The event's date or time changed.",
  }
  const TOO_MANY_PEOPLE: ReassessmentFlag = {
    kind: 'no_longer_suitable',
    reason: "Expected attendance of 250 exceeds the venue's capacity of 200.",
  }
  /** The booked event's hall, its venue still available, flagged by a change instead. */
  const changeFlaggedHall: BookingRequest = {
    ...bookedHall,
    needs_alternative_venue: false,
    unavailability: [],
    flagged_after_change: true,
    reassessment_flags: [TIMING_CHANGED, TOO_MANY_PEOPLE],
  }

  /** Each reason listed under the arrangement, as its text. */
  function changeReasonsUnder(purpose: string): Promise<string[]> {
    return listedUnder(purpose, CHANGE_REASONS_LABEL)
  }

  function findAnotherVenueLinks(hall: HTMLElement): HTMLElement[] {
    return within(hall).queryAllByRole('link', {
      name: `Find another venue for ${bookedHall.purpose}`,
    })
  }

  it('names each reason with its kind, in the backend’s order, and offers another venue', async () => {
    listBookedEventAs([changeFlaggedHall])

    openEvent(BOOKED_EVENT.reference)

    expect(await changeReasonsUnder(bookedHall.purpose)).toEqual([
      "Requires reconfirmation: The event's date or time changed.",
      "No longer suitable: Expected attendance of 250 exceeds the venue's capacity of 200.",
    ])
    expect(findAnotherVenueLinks(await item(bookedHall.purpose))).toHaveLength(1)
  })

  it('offers one venue search when its venue is also unavailable, listing both kinds of reason', async () => {
    listBookedEventAs([
      { ...bookedHall, flagged_after_change: true, reassessment_flags: [TIMING_CHANGED] },
    ])

    openEvent(BOOKED_EVENT.reference)

    expect(await causesUnder(bookedHall.purpose)).toEqual([
      'Maintenance: Roof repairs. Unavailable from 26 Nov, 8:00 am to 26 Nov, 6:00 pm.',
    ])
    expect(await changeReasonsUnder(bookedHall.purpose)).toEqual([
      "Requires reconfirmation: The event's date or time changed.",
    ])
    expect(findAnotherVenueLinks(await item(bookedHall.purpose))).toHaveLength(1)
  })

  it('shows no flag once it stops counting, though the backend keeps the reasons', async () => {
    listBookedEventAs([{ ...changeFlaggedHall, status: 'released', flagged_after_change: false }])

    openEvent(BOOKED_EVENT.reference)

    const hall = await item(bookedHall.purpose)
    expect(hall).toHaveTextContent('Released')
    expect(within(hall).queryByRole('list', { name: CHANGE_REASONS_LABEL })).not.toBeInTheDocument()
    expect(findAnotherVenueLinks(hall)).toHaveLength(0)
  })
})
