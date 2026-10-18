import { act, screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { signedIn } from '@/store'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import { OTHER_STAFF } from '../test/otherStaff'

const VENUE_STAFF = mockSessionFor(MOCK_ACCOUNTS.venueStaff)
const COORDINATOR = mockSessionFor(MOCK_ACCOUNTS.coordinator)
/** Marina Hall over 10 and 11 Nov, written out so a wrong path builder can't agree with itself. */
const MARINA_TWO_DAYS = '/venues/1?from=2026-11-10&to=2026-11-11'

/** The text of each period listed under one day, found by the day's heading. */
async function periodsOn(dayName: string): Promise<(string | null)[]> {
  const day = await screen.findByRole('region', { name: dayName })
  return within(day)
    .queryAllByRole('listitem')
    .map((period) => period.textContent)
}

/** The calendar request's range, as the backend received it. */
function sentRange(requests: Request[]) {
  const sent = requests.find((request) => request.url.includes('/calendar'))
  const query = new URL(sent?.url ?? 'http://none').searchParams
  return { start: query.get('range_start'), end: query.get('range_end') }
}

describe('SCRUM-26 a venue’s availability, day by day (AC1, AC2)', () => {
  it('lists every day chosen with what holds the venue, padded bookings showing their event’s times', async () => {
    renderApp(MARINA_TWO_DAYS, { session: VENUE_STAFF })

    expect(await periodsOn('Tuesday 10 Nov')).toEqual([
      'Booked 8:30 am – 12:30 pm Event #101 Event 9:00 am – 12:00 pm',
      'Tentative 11:30 am – 1:30 pm Event #104 Event 12:00 pm – 1:00 pm',
      'Booked 12:30 pm – 5:30 pm Event #105 Event 1:00 pm – 5:00 pm',
      'Blocked 5:30 pm – 8:00 pm Stage lighting repair',
    ])
    const nextDay = await screen.findByRole('region', { name: 'Wednesday 11 Nov' })
    expect(nextDay).toHaveTextContent('Nothing booked or blocked.')
  })

  it('asks for the days chosen as whole days in business time', async () => {
    const requests = recordRequests()
    renderApp(MARINA_TWO_DAYS, { session: VENUE_STAFF })

    await screen.findByRole('region', { name: 'Tuesday 10 Nov' })

    expect(sentRange(requests)).toEqual({
      start: '2026-11-10T00:00:00',
      end: '2026-11-12T00:00:00',
    })
  })

  it('puts a period that runs past midnight under both days it touches', async () => {
    server.use(
      http.get('/api/venues/1/calendar', () =>
        HttpResponse.json([
          {
            start_time: '2026-11-10T22:00:00+08:00',
            end_time: '2026-11-11T03:00:00+08:00',
            event_start: null,
            event_end: null,
            kind: 'block',
            reason: 'Overnight rigging',
          },
        ]),
      ),
    )
    renderApp(MARINA_TWO_DAYS, { session: VENUE_STAFF })

    const overnight = 'Blocked 10:00 pm – Wed 3:00 am Overnight rigging'
    expect(await periodsOn('Tuesday 10 Nov')).toEqual([overnight])
    expect(await periodsOn('Wednesday 11 Nov')).toEqual([overnight])
  })

  it('opens on the week from today when the address names no days', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    // 1 am on 3 Dec in Singapore, still 2 Dec in UTC: the week starts on the business day.
    vi.setSystemTime(new Date('2026-12-02T17:00:00Z'))
    const requests = recordRequests()
    renderApp('/venues/1', { session: VENUE_STAFF })

    expect(await screen.findByLabelText('From')).toHaveValue('2026-12-03')
    expect(screen.getByLabelText('To')).toHaveValue('2026-12-09')
    await screen.findByRole('region', { name: 'Thursday 3 Dec' })
    expect(sentRange(requests)).toEqual({
      start: '2026-12-03T00:00:00',
      end: '2026-12-10T00:00:00',
    })
    vi.useRealTimers()
  })

  it('shows other days once chosen, keeping them in the address', async () => {
    const { user, router } = renderApp(MARINA_TWO_DAYS, { session: VENUE_STAFF })
    await screen.findByRole('region', { name: 'Tuesday 10 Nov' })

    await user.clear(screen.getByLabelText('From'))
    await user.type(screen.getByLabelText('From'), '2026-11-12')
    await user.clear(screen.getByLabelText('To'))
    await user.type(screen.getByLabelText('To'), '2026-11-12')
    await user.click(screen.getByRole('button', { name: 'Show these days' }))

    expect(await screen.findByRole('region', { name: 'Thursday 12 Nov' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Tuesday 10 Nov' })).not.toBeInTheDocument()
    expect(router.state.location.search).toBe('?from=2026-11-12&to=2026-11-12')
  })

  it('shows the backend message under the last day when it is before the first', async () => {
    renderApp('/venues/1?from=2026-11-12&to=2026-11-10', { session: VENUE_STAFF })

    expect(await screen.findByText('range_end must be after range_start.')).toBeInTheDocument()
    expect(screen.getByLabelText('To')).toBeInvalid()
    expect(screen.queryByRole('region', { name: /Nov$/ })).not.toBeInTheDocument()
  })

  it('says it is loading, then shows the backend message when the calendar cannot be read', async () => {
    server.use(
      http.get('/api/venues/1/calendar', () =>
        HttpResponse.json(
          { error: 'internal_error', message: 'The calendar is unavailable.' },
          { status: 500 },
        ),
      ),
    )
    renderApp(MARINA_TWO_DAYS, { session: VENUE_STAFF })

    expect(await screen.findByText('Loading availability…')).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('The calendar is unavailable.')
  })
})

describe('SCRUM-26 what each role is told about a period (AC3)', () => {
  it.each(OTHER_STAFF)('shows $full_name the reasons the backend gives them', async (account) => {
    renderApp(MARINA_TWO_DAYS, { session: mockSessionFor(account) })

    const periods = await periodsOn('Tuesday 10 Nov')

    expect(periods.map((period) => period?.includes(' booking ') ?? false)).toEqual([
      true,
      true,
      true,
      false,
    ])
    expect(periods[3]).toBe('Blocked 5:30 pm – 8:00 pm maintenance')
  })

  it('reads the calendar again when someone else signs in', async () => {
    const { store } = renderApp(MARINA_TWO_DAYS, { session: COORDINATOR })
    expect((await periodsOn('Tuesday 10 Nov'))[3]).toBe('Blocked 5:30 pm – 8:00 pm maintenance')

    act(() => {
      store.dispatch(signedIn(VENUE_STAFF))
    })

    expect(await screen.findByText('Stage lighting repair')).toBeInTheDocument()
  })
})
