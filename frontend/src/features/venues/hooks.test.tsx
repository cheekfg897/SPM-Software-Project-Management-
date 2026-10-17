import { screen, waitFor } from '@testing-library/react'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { MOCK_VENUES } from '@/mocks/handlers/venueFixtures'
import { renderHookWithProviders, renderWithProviders } from '@/test/render'

import type { VenueDetails } from './api'
import {
  useCreateVenue,
  useIsVenueStaff,
  useUpdateVenue,
  useVenue,
  useVenueCalendar,
  useVenues,
} from './hooks'

const MARQUEE = MOCK_VENUES.lawnMarquee
const SESSION = { session: mockSessionFor(MOCK_ACCOUNTS.venueStaff) }

const SKYLINE_ROOM: VenueDetails = {
  name: 'Skyline Room',
  location: 'Level 9',
  capacity: 64,
  facilities: [],
  accessibility_features: [],
  supported_layouts: [],
  opening_hours: [],
}

/**
 * Keeps the list and one venue on screen while it adds a venue and renames another, as a page
 * would, so a change that didn't read them again would leave the old answers showing.
 */
function VenuesProbe() {
  const venues = useVenues()
  const marquee = useVenue(MARQUEE.id)
  const create = useCreateVenue()
  const update = useUpdateVenue(MARQUEE.id)
  return (
    <div>
      <p>{venues.data ? `${venues.data.length} venues` : 'loading the list'}</p>
      <p>{marquee.data ? `Called ${marquee.data.name}` : 'loading the venue'}</p>
      <button type="button" onClick={() => create.mutate(SKYLINE_ROOM)}>
        Add
      </button>
      <button
        type="button"
        onClick={() => update.mutate({ ...SKYLINE_ROOM, name: 'Lawn Pavilion' })}
      >
        Rename
      </button>
    </div>
  )
}

describe('SCRUM-25 who the venue pages treat as Venue Staff (AC4)', () => {
  it.each([
    { name: 'Venue Staff', options: SESSION, expected: true },
    {
      name: 'a coordinator',
      options: { session: mockSessionFor(MOCK_ACCOUNTS.coordinator) },
      expected: false,
    },
    { name: 'nobody signed in', options: {}, expected: false },
  ])('answers $expected for $name', ({ options, expected }) => {
    const { result } = renderHookWithProviders(useIsVenueStaff, options)

    expect(result.current).toBe(expected)
  })
})

describe('SCRUM-26 the calendar hook', () => {
  it('asks the backend even with nobody signed in, and shows its refusal', async () => {
    const range = { range_start: '2026-11-10T00:00:00', range_end: '2026-11-11T00:00:00' }

    const { result } = renderHookWithProviders(() => useVenueCalendar(MARQUEE.id, range))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toMatchObject({ status: 401 })
  })
})

describe('SCRUM-25 venue hooks read the venues again after a change (AC3)', () => {
  it('shows a venue added while the list is on screen', async () => {
    const { user } = renderWithProviders(<VenuesProbe />, SESSION)
    expect(await screen.findByText('7 venues')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add' }))

    expect(await screen.findByText('8 venues')).toBeInTheDocument()
  })

  it('shows a venue’s new name while it is on screen', async () => {
    const { user } = renderWithProviders(<VenuesProbe />, SESSION)
    expect(await screen.findByText('Called Lawn Marquee')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Rename' }))

    expect(await screen.findByText('Called Lawn Pavilion')).toBeInTheDocument()
  })
})
