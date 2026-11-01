import { screen, waitFor, within } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'

import { coordinatorEventPath, organiserRequestPath } from '@/config/routes'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import {
  findRegion,
  serveRecordInStatus,
  serveRecordWithStatus,
  statusShownFor,
} from '../test/recordPage'

/**
 * SCRUM-61: an Event Organiser cancels their event from its page, with a reason, after saying
 * yes to a second question that names what is released and how many registered attendees are
 * told, and that it can't be undone (Product Owner, 29 Oct; ADR-0122). Offered from submitted to
 * confirmed, and never to the coordinator. The mock in src/mocks/handlers/eventPlanning.ts
 * answers the route as the backend does.
 *
 * Omar has EVR-Q4ZT6N1B, submitted with no one registered. Sara's organisation has EVR-BOOK0102,
 * confirmed, with three attendees registered and one withdrawn.
 */

const OMAR = MOCK_ACCOUNTS.organiser
const SARA = MOCK_ACCOUNTS.otherOrganiser
const SUBMITTED = 'EVR-Q4ZT6N1B'
const CONFIRMED_WITH_ATTENDEES = 'EVR-BOOK0102'
const REASON = 'Our keynote speaker has withdrawn.'
const CARD = 'Cancel the event'

const CANCELLABLE: EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.SUBMITTED,
  EVENT_REQUEST_STATUS.UNDER_REVIEW,
  EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
  EVENT_REQUEST_STATUS.CONFIRMED,
]
const NOT_CANCELLABLE = Object.values(EVENT_REQUEST_STATUS).filter(
  (status) => !CANCELLABLE.includes(status),
)

function openAsOmar(reference: string) {
  return renderApp(organiserRequestPath(reference), { session: mockSessionFor(OMAR) })
}

function openAsSara(reference: string) {
  return renderApp(organiserRequestPath(reference), { session: mockSessionFor(SARA) })
}

/** Open the event as Omar, type the reason and press Cancel event, so the page asks first. */
async function startCancelling(reference: string) {
  const opened = openAsOmar(reference)
  await opened.user.type(await screen.findByLabelText('Reason for cancelling'), REASON)
  await opened.user.click(screen.getByRole('button', { name: 'Cancel event' }))
  return opened
}

/** Whether the page offers the organiser the cancel action, once the record has loaded. */
async function offersCancelling(): Promise<boolean> {
  await screen.findByRole('region', { name: 'About the event' })
  return screen.queryByRole('region', { name: CARD }) !== null
}

describe('SCRUM-61 where the organiser is offered Cancel event', () => {
  it.each(CANCELLABLE)('offers it on an event that is %s', async (status) => {
    await serveRecordInStatus(OMAR, SUBMITTED, status)
    openAsOmar(SUBMITTED)

    expect(await offersCancelling()).toBe(true)
  })

  it.each(NOT_CANCELLABLE)('offers nothing on an event that is %s', async (status) => {
    await serveRecordInStatus(OMAR, SUBMITTED, status)
    openAsOmar(SUBMITTED)

    expect(await offersCancelling()).toBe(false)
  })

  it('never offers it to the coordinator: only the organiser cancels', async () => {
    renderApp(coordinatorEventPath(CONFIRMED_WITH_ATTENDEES), {
      session: mockSessionFor(MOCK_ACCOUNTS.coordinator),
    })

    expect(await offersCancelling()).toBe(false)
  })
})

describe('SCRUM-61 cancelling an event from its page', () => {
  it('asks first, saying it is final and what is released, and sends nothing when kept', async () => {
    const requests = recordRequests()
    const { user } = await startCancelling(SUBMITTED)

    const card = await findRegion(CARD)
    expect(card).toHaveTextContent("This can't be undone.")
    expect(card).toHaveTextContent(
      'Its venue bookings and holds are released and its reserved equipment returned.',
    )
    expect(card).toHaveTextContent('No attendee has registered.')
    await user.click(within(card).getByRole('button', { name: 'Keep the event' }))

    expect(within(card).getByRole('button', { name: 'Cancel event' })).toBeInTheDocument()
    expect(requests.filter((request) => request.method === 'POST')).toEqual([])
    expect(statusShownFor(SUBMITTED)).toBe('Submitted')
  })

  it('says how many registered attendees are told, as the backend counts them', async () => {
    const { user } = openAsSara(CONFIRMED_WITH_ATTENDEES)
    await user.click(await screen.findByRole('button', { name: 'Cancel event' }))

    expect(await findRegion(CARD)).toHaveTextContent('3 registered attendees are told.')
  })

  it('says one registered attendee is told', async () => {
    server.use(
      http.get(`/api/events/requests/${SUBMITTED}/registrations`, () =>
        HttpResponse.json({ capacity: 10, registered_count: 1, places_left: 9, items: [] }),
      ),
    )
    const { user } = openAsOmar(SUBMITTED)
    await user.click(await screen.findByRole('button', { name: 'Cancel event' }))

    expect(await findRegion(CARD)).toHaveTextContent('1 registered attendee is told.')
  })

  it('leaves the attendees out when the backend could not count them, rather than guess', async () => {
    server.use(
      http.get(`/api/events/requests/${SUBMITTED}/registrations`, () =>
        HttpResponse.json({ error: 'server_error', message: 'Try again.' }, { status: 500 }),
      ),
    )
    const { user } = openAsOmar(SUBMITTED)
    await user.click(await screen.findByRole('button', { name: 'Cancel event' }))

    const card = await findRegion(CARD)
    expect(card).toHaveTextContent('Its venue bookings and holds are released')
    expect(card).not.toHaveTextContent('attendee')
  })

  it('cancels with the reason typed, and the page shows Cancelled with nothing left to cancel', async () => {
    const requests = recordRequests()
    const { user } = await startCancelling(SUBMITTED)

    await user.click(screen.getByRole('button', { name: 'Yes, cancel the event' }))

    await waitFor(() => expect(statusShownFor(SUBMITTED)).toBe('Cancelled'))
    expect(screen.queryByRole('region', { name: CARD })).not.toBeInTheDocument()
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toMatch(new RegExp(`/api/events/requests/${SUBMITTED}/cancel$`))
    expect(await sent?.json()).toEqual({ reason: REASON })
  })

  it("sends no reason when none is typed, and shows the backend's message under the box", async () => {
    const requests = recordRequests()
    const { user } = openAsOmar(SUBMITTED)
    await user.click(await screen.findByRole('button', { name: 'Cancel event' }))

    await user.click(screen.getByRole('button', { name: 'Yes, cancel the event' }))

    const reason = await screen.findByLabelText('Reason for cancelling')
    expect(await screen.findByText('A reason is required to cancel the event.')).toBeInTheDocument()
    expect(reason).toHaveAttribute('aria-invalid', 'true')
    expect(statusShownFor(SUBMITTED)).toBe('Submitted')
    const sent = requests.find((request) => request.method === 'POST')
    expect(await sent?.json()).toEqual({})
  })

  it("shows the backend's own words for a refusal, as they come", async () => {
    server.use(
      http.post(`/api/events/requests/${SUBMITTED}/cancel`, () =>
        HttpResponse.json(
          { error: 'cancellation_not_allowed', message: 'Not now, says the backend.' },
          { status: 409 },
        ),
      ),
    )
    const { user } = await startCancelling(SUBMITTED)

    await user.click(screen.getByRole('button', { name: 'Yes, cancel the event' }))

    const alert = await within(await findRegion(CARD)).findByRole('alert')
    expect(alert).toHaveTextContent('Not now, says the backend.')
  })

  it('reads the event again after a refusal, so a rejection made meanwhile shows', async () => {
    // The coordinator rejected the event while the organiser was cancelling it.
    let status: EventRequestStatus = EVENT_REQUEST_STATUS.SUBMITTED
    await serveRecordWithStatus(OMAR, SUBMITTED, () => status)
    server.use(
      http.post(`/api/events/requests/${SUBMITTED}/cancel`, () => {
        status = EVENT_REQUEST_STATUS.REJECTED
        return HttpResponse.json(
          { error: 'cancellation_not_allowed', message: "A rejected event can't be cancelled." },
          { status: 409 },
        )
      }),
    )
    const { user } = await startCancelling(SUBMITTED)

    await user.click(screen.getByRole('button', { name: 'Yes, cancel the event' }))

    await waitFor(() => expect(statusShownFor(SUBMITTED)).toBe('Rejected'))
    expect(screen.queryByRole('region', { name: CARD })).not.toBeInTheDocument()
  })

  it('says the coordinator is told the reason when one is assigned', async () => {
    openAsSara(CONFIRMED_WITH_ATTENDEES)

    expect(await findRegion(CARD)).toHaveTextContent('your coordinator is told your reason')
  })

  it('leaves the coordinator out while none is assigned, since nobody is told', async () => {
    openAsOmar(SUBMITTED)

    const card = await findRegion(CARD)

    expect(card).toHaveTextContent('It happens at once.')
    expect(card).not.toHaveTextContent('coordinator')
  })

  it('says it is busy while the event is being cancelled', async () => {
    server.use(http.post(`/api/events/requests/${SUBMITTED}/cancel`, () => delay('infinite')))
    const { user } = await startCancelling(SUBMITTED)
    const cancel = screen.getByRole('button', { name: 'Yes, cancel the event' })

    await user.click(cancel)

    expect(cancel).toBeDisabled()
    expect(cancel).toHaveAttribute('aria-busy', 'true')
  })
})
