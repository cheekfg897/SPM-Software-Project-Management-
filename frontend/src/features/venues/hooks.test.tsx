import { screen } from '@testing-library/react'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { MOCK_VENUES } from '@/mocks/handlers/venueFixtures'
import { renderWithProviders } from '@/test/render'

import type { VenueDetails } from './api'
import { useCreateVenue, useUpdateVenue, useVenue, useVenues } from './hooks'

const GARDEN = MOCK_VENUES.gardenPavilion
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
  const garden = useVenue(GARDEN.id)
  const create = useCreateVenue()
  const update = useUpdateVenue(GARDEN.id)
  return (
    <div>
      <p>{venues.data ? `${venues.data.length} venues` : 'loading the list'}</p>
      <p>{garden.data ? `Called ${garden.data.name}` : 'loading the venue'}</p>
      <button type="button" onClick={() => create.mutate(SKYLINE_ROOM)}>
        Add
      </button>
      <button
        type="button"
        onClick={() => update.mutate({ ...SKYLINE_ROOM, name: 'Garden Marquee' })}
      >
        Rename
      </button>
    </div>
  )
}

describe('SCRUM-25 venue hooks read the venues again after a change (AC3)', () => {
  it('shows a venue added while the list is on screen', async () => {
    const { user } = renderWithProviders(<VenuesProbe />, SESSION)
    expect(await screen.findByText('3 venues')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add' }))

    expect(await screen.findByText('4 venues')).toBeInTheDocument()
  })

  it('shows a venue’s new name while it is on screen', async () => {
    const { user } = renderWithProviders(<VenuesProbe />, SESSION)
    expect(await screen.findByText('Called Garden Pavilion')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Rename' }))

    expect(await screen.findByText('Called Garden Marquee')).toBeInTheDocument()
  })
})
