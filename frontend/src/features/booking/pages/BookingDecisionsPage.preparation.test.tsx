import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

const APPROVED_URL = '/api/venues/booking-requests/approved'
const SAFETY_APPROVAL_MESSAGE =
  "Preparation details can't be recorded until the Safety Officer has approved the event's" +
  ' Operational Safety Check.'

function renderPage() {
  return renderApp(ROUTES.BOOKING_DECISIONS, {
    session: mockSessionFor(MOCK_ACCOUNTS.venueStaff),
  })
}

/** The approved bookings section, once its list has loaded. */
async function findApprovedSection() {
  const section = await screen.findByRole('region', { name: 'Approved bookings' })
  await within(section).findAllByRole('article')
  return within(section)
}

/**
 * One approved booking, found by the purpose its heading gives it. The queue above may hold a
 * request with the same purpose, so the search stays inside the approved bookings.
 */
async function findBooking(purpose: string) {
  const approved = await findApprovedSection()
  return within(approved.getByRole('article', { name: purpose }))
}

/** The PUT the page sent, read as JSON. */
async function sentPreparation(requests: Request[]) {
  const update = requests.find((sent) => sent.method === 'PUT')
  const body: unknown = await update?.json()
  return { url: update?.url, body }
}

describe("SCRUM-84 Venue Staff record a booking's preparation", () => {
  it('lists the approved bookings, the earliest event first, with what is recorded', async () => {
    renderPage()
    const approved = await findApprovedSection()

    const purposes = approved
      .getAllByRole('heading', { level: 3 })
      .map((entry) => entry.textContent)

    // The Auditorium is flagged as needing an alternative venue but still approved (SCRUM-92).
    // The confirmed gala's two come last, by id, as they share its date and start.
    expect(purposes).toEqual([
      'Grand ballroom',
      'Exhibition hall',
      'Main hall',
      'Auditorium',
      'Gala dinner',
      'Drinks reception',
    ])
    const ballroom = await findBooking('Grand ballroom')
    expect(ballroom.getByText('Preparation: In progress')).toBeInTheDocument()
    expect(ballroom.getByText('Preparation notes: Stage half built.')).toBeInTheDocument()
    expect(ballroom.getByText(/2026-11-12/)).toBeInTheDocument()
  })

  it('starts the form from what is recorded', async () => {
    renderPage()
    const ballroom = await findBooking('Grand ballroom')

    expect(ballroom.getByLabelText('Preparation status for Grand ballroom')).toHaveValue(
      'in_progress',
    )
    expect(ballroom.getByLabelText('Preparation notes for Grand ballroom')).toHaveValue(
      'Stage half built.',
    )
  })

  it('sends the status and notes, then shows what the backend saved (AC1)', async () => {
    const requests = recordRequests()
    const { user } = renderPage()
    const ballroom = await findBooking('Grand ballroom')

    await user.selectOptions(ballroom.getByLabelText(/^Preparation status/), 'Ready')
    await user.clear(ballroom.getByLabelText(/^Preparation notes/))
    await user.type(ballroom.getByLabelText(/^Preparation notes/), 'Stage built, chairs out.')
    await user.click(ballroom.getByRole('button', { name: 'Save preparation for Grand ballroom' }))

    expect(await ballroom.findByText('Preparation: Ready')).toBeInTheDocument()
    expect(ballroom.getByText('Preparation notes: Stage built, chairs out.')).toBeInTheDocument()
    expect(ballroom.getByRole('status')).toHaveTextContent('Preparation saved.')
    const sent = await sentPreparation(requests)
    expect(sent.url).toContain('/api/venues/booking-requests/9109/preparation')
    expect(sent.body).toEqual({ status: 'ready', notes: 'Stage built, chairs out.' })
  })

  it('leaves empty notes out, which clears them', async () => {
    const requests = recordRequests()
    const { user } = renderPage()
    const ballroom = await findBooking('Grand ballroom')

    await user.clear(ballroom.getByLabelText(/^Preparation notes/))
    await user.click(ballroom.getByRole('button', { name: /^Save preparation/ }))

    await waitFor(() => expect(ballroom.queryByText(/^Preparation notes:/)).toBeNull())
    expect((await sentPreparation(requests)).body).toEqual({ status: 'in_progress' })
  })

  it("shows the backend's refusal before the Safety Officer has approved the event (AC5)", async () => {
    const { user } = renderPage()
    const hall = await findBooking('Main hall')

    await user.selectOptions(hall.getByLabelText(/^Preparation status/), 'In progress')
    await user.click(hall.getByRole('button', { name: /^Save preparation/ }))

    expect(await hall.findByRole('alert')).toHaveTextContent(SAFETY_APPROVAL_MESSAGE)
    expect(hall.getByText('Preparation: Not started')).toBeInTheDocument()
  })

  it("shows the backend's message under the notes it refuses", async () => {
    const { user } = renderPage()
    const ballroom = await findBooking('Grand ballroom')

    await user.clear(ballroom.getByLabelText(/^Preparation notes/))
    await user.type(ballroom.getByLabelText(/^Preparation notes/), '   ')
    await user.click(ballroom.getByRole('button', { name: /^Save preparation/ }))

    expect(await ballroom.findByText('Must not be blank.')).toBeInTheDocument()
    expect(ballroom.queryByRole('alert')).toBeNull()
  })

  it('lists a request approved in the queue among the approved bookings', async () => {
    const { user } = renderPage()
    const queue = within(screen.getByRole('region', { name: 'Waiting for a decision' }))
    const breakout = within(await queue.findByRole('article', { name: 'Breakout room' }))

    await user.click(breakout.getByRole('button', { name: /^Approve/ }))

    const approved = within(screen.getByRole('region', { name: 'Approved bookings' }))
    expect(await approved.findByRole('article', { name: 'Breakout room' })).toBeInTheDocument()
  })

  it('says so when no booking is approved', async () => {
    server.use(http.get(APPROVED_URL, () => HttpResponse.json([])))
    renderPage()

    const section = await screen.findByRole('region', { name: 'Approved bookings' })

    expect(await within(section).findByText('No approved bookings to prepare.')).toBeInTheDocument()
  })
})
