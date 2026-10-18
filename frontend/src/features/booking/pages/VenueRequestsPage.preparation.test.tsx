import { screen, within } from '@testing-library/react'

import { venueRequestsPath } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { MOCK_BOOKING_EVENTS } from '@/mocks/handlers/bookingFixtures'
import { renderApp } from '@/test/render'

/** One of the event's requests on the coordinator's page, found by its purpose. */
async function findRequest(reference: string, purpose: string) {
  renderApp(venueRequestsPath(reference), {
    session: mockSessionFor(MOCK_ACCOUNTS.coordinator),
  })
  return within(await screen.findByRole('listitem', { name: purpose }))
}

describe("SCRUM-84 the coordinator sees each approved booking's preparation", () => {
  it('shows the status and notes Venue Staff recorded (AC2)', async () => {
    const ballroom = await findRequest(
      MOCK_BOOKING_EVENTS.safetyApproved.reference,
      'Grand ballroom',
    )

    expect(ballroom.getByText('Preparation: In progress')).toBeInTheDocument()
    expect(ballroom.getByText('Preparation notes: Stage half built.')).toBeInTheDocument()
  })

  it('shows no preparation on a request that is not approved', async () => {
    const breakout = await findRequest(
      MOCK_BOOKING_EVENTS.earlierWorkshop.reference,
      'Breakout room',
    )

    expect(breakout.queryByText(/^Preparation/)).toBeNull()
  })
})
