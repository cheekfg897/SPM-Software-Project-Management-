import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { REJECTION_REASON_REQUIRED_MESSAGE } from '@/mocks/handlers/booking'
import { MOCK_ARRANGEMENTS } from '@/mocks/handlers/bookingFixtures'
import { errorResponse } from '@/mocks/responses'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

/**
 * SCRUM-59 on Venue Staff's booking page: each booking a change flagged, with why, the new period
 * the backend pre-fills and the occupancy it gives it, to reconfirm or reject. The mock's moved
 * event has three: an approved plenary hall that held everyone, a workshop room still waiting for
 * a decision, and an approved stage too small for the new attendance.
 */

const FLAGGED_URL = '/api/venues/booking-requests/flagged'
const HALL = MOCK_ARRANGEMENTS.movedHall
const LOADING_TEXT = 'Loading flagged bookings…'

function flaggedSection() {
  return within(screen.getByRole('region', { name: 'Flagged after a change' }))
}

async function findFlagged(purpose: string) {
  return within(await flaggedSection().findByRole('article', { name: purpose }))
}

function renderPage() {
  return renderApp(ROUTES.BOOKING_DECISIONS, {
    session: mockSessionFor(MOCK_ACCOUNTS.venueStaff),
  })
}

describe('SCRUM-59 flagged bookings on the venue booking page', () => {
  it('lists each flagged booking in the order the backend sends them, with why', async () => {
    renderPage()
    const hall = await findFlagged('Plenary hall')

    const purposes = flaggedSection()
      .getAllByRole('heading', { level: 3 })
      .map((entry) => entry.textContent)
    expect(purposes).toEqual(['Plenary hall', 'Workshop room', 'Stage'])
    expect(
      hall.getByText("Requires reconfirmation: The event's date or time changed."),
    ).toBeVisible()
    expect(
      hall.getByText(
        "Requires reconfirmation: The event's expected attendance rose from 80 to 120, above this arrangement's expected occupancy of 80.",
      ),
    ).toBeVisible()
  })

  it('says it is loading until the list arrives', async () => {
    renderPage()

    expect(flaggedSection().getByText(LOADING_TEXT)).toBeInTheDocument()
    await findFlagged('Plenary hall')
    expect(flaggedSection().queryByText(LOADING_TEXT)).not.toBeInTheDocument()
  })

  it('says so when nothing is flagged', async () => {
    server.use(http.get(FLAGGED_URL, () => HttpResponse.json([])))
    renderPage()

    expect(
      await flaggedSection().findByText('No bookings are flagged after a change.'),
    ).toBeInTheDocument()
  })

  it('starts the form from the period and occupancy the backend gives it, in Singapore time', async () => {
    renderPage()
    const hall = await findFlagged('Plenary hall')

    expect(hall.getByLabelText('New start for Plenary hall')).toHaveValue('2026-11-16T09:00')
    expect(hall.getByLabelText('New end for Plenary hall')).toHaveValue('2026-11-16T12:00')
    expect(hall.getByLabelText('New start for Plenary hall')).not.toHaveAttribute('readonly')
    expect(hall.getByText('Expected occupancy once reconfirmed: 120')).toBeInTheDocument()
  })

  it("shows the period read-only when the event's date and times haven't changed", async () => {
    server.use(
      http.get(FLAGGED_URL, () =>
        HttpResponse.json([
          {
            booking: HALL,
            reconfirm_with: {
              starts_at: '2026-11-15T09:00:00+08:00',
              ends_at: '2026-11-15T12:00:00+08:00',
              expected_occupancy: 80,
              period_adjustable: false,
            },
          },
        ]),
      ),
    )
    renderPage()
    const hall = await findFlagged('Plenary hall')

    expect(hall.getByLabelText('New start for Plenary hall')).toHaveAttribute('readonly')
    expect(hall.getByLabelText('New end for Plenary hall')).toHaveAttribute('readonly')
    expect(
      hall.getByText("The event's date and times haven't changed, so the period stays."),
    ).toBeInTheDocument()
  })

  it('says a request still waiting for a decision only moves', async () => {
    renderPage()
    const workshop = await findFlagged('Workshop room')

    expect(
      workshop.getByText(
        'Still waiting for a decision: reconfirming moves it to the new period, and it is then decided in the queue above.',
      ),
    ).toBeInTheDocument()
  })

  it('says a Conflicting request still waiting for a decision only moves too', async () => {
    const workshop = MOCK_ARRANGEMENTS.movedWorkshop
    server.use(
      http.get(FLAGGED_URL, () =>
        HttpResponse.json([
          {
            booking: { ...workshop, status: 'conflicting' },
            reconfirm_with: {
              starts_at: '2026-11-16T13:00:00+08:00',
              ends_at: '2026-11-16T15:00:00+08:00',
              expected_occupancy: 10,
              period_adjustable: true,
            },
          },
        ]),
      ),
    )
    renderPage()
    const conflicting = await findFlagged('Workshop room')

    expect(
      conflicting.getByText(
        'Still waiting for a decision: reconfirming moves it to the new period, and it is then decided in the queue above.',
      ),
    ).toBeInTheDocument()
  })

  it('reconfirms for the pre-filled period with no reason, and the booking leaves the list', async () => {
    const requests = recordRequests()
    const { user } = renderPage()
    const hall = await findFlagged('Plenary hall')

    await user.click(hall.getByRole('button', { name: 'Reconfirm Plenary hall' }))

    await waitFor(() =>
      expect(flaggedSection().queryByRole('article', { name: 'Plenary hall' })).toBeNull(),
    )
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toContain(`/api/venues/booking-requests/${String(HALL.id)}/reconfirm`)
    await expect(sent?.json()).resolves.toEqual({
      starts_at: '2026-11-16T09:00:00+08:00',
      ends_at: '2026-11-16T12:00:00+08:00',
    })
  })

  it('sends an adjusted period and a reason', async () => {
    const requests = recordRequests()
    const { user } = renderPage()
    const stage = await findFlagged('Stage')

    await user.clear(stage.getByLabelText('New start for Stage'))
    await user.type(stage.getByLabelText('New start for Stage'), '2026-11-16T15:00')
    await user.type(stage.getByLabelText('Reason for Stage'), 'Standing room agreed.')
    await user.click(stage.getByRole('button', { name: 'Reconfirm Stage' }))

    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))
    const sent = requests.find((request) => request.method === 'POST')
    await expect(sent?.json()).resolves.toEqual({
      starts_at: '2026-11-16T15:00:00+08:00',
      ends_at: '2026-11-16T17:00:00+08:00',
      reason: 'Standing room agreed.',
    })
  })

  it("shows the backend's field error when a venue too small needs a reason", async () => {
    const { user } = renderPage()
    const stage = await findFlagged('Stage')

    await user.click(stage.getByRole('button', { name: 'Reconfirm Stage' }))

    expect(
      await stage.findByText(
        "A reason is required because the venue's capacity of 20 is below the booking's expected occupancy of 120.",
      ),
    ).toBeInTheDocument()
    expect(stage.getByLabelText('Reason for Stage')).toHaveAttribute('aria-invalid', 'true')
  })

  it("shows the backend's 409 message, and reads the list again after the refusal", async () => {
    const message = 'Cannot reconfirm: replacement request #12 for this booking is still waiting.'
    server.use(
      http.post('/api/venues/booking-requests/:requestId/reconfirm', () =>
        errorResponse(409, 'conflict', message),
      ),
    )
    const requests = recordRequests()
    const { user } = renderPage()
    const hall = await findFlagged('Plenary hall')

    await user.click(hall.getByRole('button', { name: 'Reconfirm Plenary hall' }))

    expect(await hall.findByText(message)).toBeInTheDocument()
    await waitFor(() =>
      expect(requests.filter((request) => request.url.endsWith(FLAGGED_URL))).toHaveLength(2),
    )
  })

  it("shows the backend's field error when a rejection has no reason", async () => {
    const { user } = renderPage()
    const hall = await findFlagged('Plenary hall')

    await user.click(hall.getByRole('button', { name: 'Reject Plenary hall' }))

    expect(await hall.findByText(REJECTION_REASON_REQUIRED_MESSAGE)).toBeInTheDocument()
  })

  it('rejects with the reason, and the booking leaves the list', async () => {
    const requests = recordRequests()
    const { user } = renderPage()
    const hall = await findFlagged('Plenary hall')

    await user.type(hall.getByLabelText('Reason for Plenary hall'), 'Hall closed that week.')
    await user.click(hall.getByRole('button', { name: 'Reject Plenary hall' }))

    await waitFor(() =>
      expect(flaggedSection().queryByRole('article', { name: 'Plenary hall' })).toBeNull(),
    )
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.url).toContain(`/api/venues/booking-requests/${String(HALL.id)}/reject`)
    await expect(sent?.json()).resolves.toEqual({ reason: 'Hall closed that week.' })
  })

  it("shows the rejection's own error, not the reconfirmation's before it", async () => {
    const tooSmall =
      "A reason is required because the venue's capacity of 20 is below the booking's expected occupancy of 120."
    const { user } = renderPage()
    const stage = await findFlagged('Stage')
    await user.click(stage.getByRole('button', { name: 'Reconfirm Stage' }))
    await stage.findByText(tooSmall)

    await user.click(stage.getByRole('button', { name: 'Reject Stage' }))

    expect(await stage.findByText(REJECTION_REASON_REQUIRED_MESSAGE)).toBeInTheDocument()
    expect(stage.queryByText(tooSmall)).not.toBeInTheDocument()
  })

  it('clears the other action error once Venue Staff try again', async () => {
    const { user } = renderPage()
    const hall = await findFlagged('Plenary hall')
    await user.click(hall.getByRole('button', { name: 'Reject Plenary hall' }))
    await hall.findByText(REJECTION_REASON_REQUIRED_MESSAGE)

    await user.click(hall.getByRole('button', { name: 'Reconfirm Plenary hall' }))

    await waitFor(() =>
      expect(flaggedSection().queryByRole('article', { name: 'Plenary hall' })).toBeNull(),
    )
  })
})
