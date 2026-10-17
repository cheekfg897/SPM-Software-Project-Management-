import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { MOCK_VENUES } from '@/mocks/handlers/venueFixtures'
import { server } from '@/mocks/server'
import { renderApp } from '@/test/render'

import { retype } from '../test/venueFormSteps'

const VENUE_STAFF = mockSessionFor(MOCK_ACCOUNTS.venueStaff)
/** Marina Hall's pages, written out so a wrong path builder can't agree with itself. */
const MARINA_PAGE = '/venues/1'
const MARINA_EDIT_PAGE = '/venues/1/edit'
const REPORT_NAME = 'Saved, but some bookings now overlap'

async function changeMarinaHall(label: string, minutes: string) {
  const app = renderApp(MARINA_EDIT_PAGE, { session: VENUE_STAFF })
  await retype(app.user, await screen.findByLabelText(label), minutes)
  await app.user.click(screen.getByRole('button', { name: 'Save changes' }))
  return app
}

describe('SCRUM-67 what a new setup or turnaround time now overlaps (AC4, ADR-0033)', () => {
  it('saves, then names each overlap the backend reported and when it is', async () => {
    const { router } = await changeMarinaHall('Turnaround time (minutes)', '45')

    const report = await screen.findByRole('region', { name: REPORT_NAME })
    const lines = within(report)
      .getAllByRole('listitem')
      .map((line) => line.textContent)
    expect(lines).toEqual([
      'Bookings 512 and 511 overlap on 10 Nov, 12:30 pm – 12:45 pm',
      'Booking 511 runs into block 71 on 10 Nov, 5:30 pm – 5:45 pm',
    ])
    expect(report).toHaveTextContent('nothing has been changed or cancelled')
    expect(router.state.location.pathname).toBe(MARINA_EDIT_PAGE)
  })

  it('leads back to the venue, which shows the new time', async () => {
    const { user, router } = await changeMarinaHall('Turnaround time (minutes)', '45')

    const report = await screen.findByRole('region', { name: REPORT_NAME })
    await user.click(within(report).getByRole('link', { name: 'Back to the venue' }))

    expect(router.state.location.pathname).toBe(MARINA_PAGE)
    const buffers = await screen.findByRole('region', { name: 'Setup and turnaround' })
    expect(buffers).toHaveTextContent('45 minutes')
  })

  it('lists only the kind of overlap there is', async () => {
    await changeMarinaHall('Setup time (minutes)', '31')

    const report = await screen.findByRole('region', { name: REPORT_NAME })

    expect(within(report).getAllByRole('listitem')).toHaveLength(1)
    expect(report).toHaveTextContent('Bookings 512 and 511 overlap on 10 Nov, 12:29 pm – 12:30 pm')
  })

  it('names only the block overlap when that is all the backend reported', async () => {
    server.use(
      http.patch(`/api/venues/${MOCK_VENUES.marinaHall.id}`, () =>
        HttpResponse.json({
          ...MOCK_VENUES.marinaHall,
          overlap_warnings: [],
          block_overlap_warnings: [
            {
              booking_id: 640,
              block_id: 93,
              overlap_start: '2026-12-02T08:00:00+08:00',
              overlap_end: '2026-12-02T08:20:00+08:00',
            },
          ],
        }),
      ),
    )
    await changeMarinaHall('Setup time (minutes)', '50')

    const report = await screen.findByRole('region', { name: REPORT_NAME })

    expect(
      within(report)
        .getAllByRole('listitem')
        .map((line) => line.textContent),
    ).toEqual(['Booking 640 runs into block 93 on 2 Dec, 8:00 am – 8:20 am'])
  })

  it('goes straight back to the venue when a new time overlaps nothing', async () => {
    const { router } = await changeMarinaHall('Setup time (minutes)', '0')

    await waitFor(() => expect(router.state.location.pathname).toBe(MARINA_PAGE))
    expect(screen.queryByRole('region', { name: REPORT_NAME })).not.toBeInTheDocument()
  })
})
