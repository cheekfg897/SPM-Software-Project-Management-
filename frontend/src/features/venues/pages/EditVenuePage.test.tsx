import { screen, waitFor } from '@testing-library/react'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { MOCK_VENUES } from '@/mocks/handlers/venueFixtures'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import { bodyOf, period, periodCount, retype } from '../test/venueFormSteps'

const VENUE_STAFF = mockSessionFor(MOCK_ACCOUNTS.venueStaff)
const MARQUEE = MOCK_VENUES.lawnMarquee
/** Lawn Marquee's pages, written out so a wrong path builder can't agree with itself. */
const MARQUEE_PAGE = '/venues/27'
const MARQUEE_EDIT_PAGE = '/venues/27/edit'
const OTHER_STAFF = [MOCK_ACCOUNTS.coordinator, MOCK_ACCOUNTS.lead, MOCK_ACCOUNTS.technicalSupport]

function openEditForm() {
  return renderApp(MARQUEE_EDIT_PAGE, { session: VENUE_STAFF })
}

async function waitForTheForm() {
  return screen.findByRole('heading', { level: 1, name: 'Edit Lawn Marquee' })
}

describe('SCRUM-25 editing a venue', () => {
  it('starts from what the venue holds', async () => {
    openEditForm()
    await waitForTheForm()

    expect(screen.getByLabelText('Name')).toHaveValue('Lawn Marquee')
    expect(screen.getByLabelText('Location')).toHaveValue('East Lawn')
    expect(screen.getByLabelText('Capacity')).toHaveValue(120)
    expect(screen.getByRole('checkbox', { name: 'Banquet' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Exhibition' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Theatre' })).not.toBeChecked()
    expect(screen.getByLabelText('Facilities')).toHaveValue('sound system')
    expect(screen.getByLabelText('Accessibility features')).toHaveValue('')
    expect(screen.getByLabelText('Setup time (minutes)')).toHaveValue(45)
    expect(screen.getByLabelText('Turnaround time (minutes)')).toHaveValue(15)
    expect(periodCount()).toBe(5)
    expect(period(5).getByLabelText('Opens on')).toHaveValue('friday')
    expect(period(5).getByLabelText('Opens at')).toHaveValue('08:00')
  })

  it('puts each item of a list on its own line', async () => {
    renderApp('/venues/1/edit', { session: VENUE_STAFF })

    expect(await screen.findByLabelText('Accessibility features')).toHaveValue(
      'step-free access\nhearing loop',
    )
  })

  it('sends every field and goes back to the venue, showing the change (AC3)', async () => {
    const requests = recordRequests()
    const { user, router } = openEditForm()
    await waitForTheForm()

    await retype(user, screen.getByLabelText('Name'), 'Lawn Pavilion')
    await retype(user, screen.getByLabelText('Capacity'), '150')
    await user.click(screen.getByRole('checkbox', { name: 'Banquet' }))
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(router.state.location.pathname).toBe(MARQUEE_PAGE))
    expect(await bodyOf(requests, 'PATCH')).toEqual({
      name: 'Lawn Pavilion',
      location: 'East Lawn',
      capacity: 150,
      facilities: ['sound system'],
      accessibility_features: [],
      supported_layouts: ['exhibition'],
      setup_minutes: 45,
      turnaround_minutes: 15,
      opening_hours: MARQUEE.opening_hours,
    })
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Lawn Pavilion' }),
    ).toBeInTheDocument()
  })

  it('refuses an emptied name and capacity with the backend messages (AC2)', async () => {
    const { user, router } = openEditForm()
    await waitForTheForm()

    await user.clear(screen.getByLabelText('Name'))
    await user.clear(screen.getByLabelText('Capacity'))
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Field may not be null.')).toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toHaveAccessibleDescription('Must not be blank.')
    expect(router.state.location.pathname).toBe(MARQUEE_EDIT_PAGE)
  })

  it('refuses a capacity of 0 with the backend message (AC2)', async () => {
    const { user } = openEditForm()
    await waitForTheForm()

    await retype(user, screen.getByLabelText('Capacity'), '0')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Capacity must be a positive number.')).toBeInTheDocument()
  })

  it('shows the backend message for a venue that does not exist', async () => {
    renderApp('/venues/4242/edit', { session: VENUE_STAFF })

    expect(await screen.findByRole('alert')).toHaveTextContent('Venue not found.')
  })
})

describe('SCRUM-25 who may edit a venue (AC4)', () => {
  it('shows Venue Staff an Edit link on the venue page', async () => {
    const { user, router } = renderApp(MARQUEE_PAGE, { session: VENUE_STAFF })

    await user.click(await screen.findByRole('link', { name: 'Edit venue' }))

    expect(router.state.location.pathname).toBe(MARQUEE_EDIT_PAGE)
  })

  it.each(OTHER_STAFF)('shows $full_name the venue read-only', async (account) => {
    renderApp(MARQUEE_PAGE, { session: mockSessionFor(account) })
    await screen.findByRole('heading', { level: 1, name: 'Lawn Marquee' })

    expect(screen.queryByRole('link', { name: 'Edit venue' })).not.toBeInTheDocument()
  })

  it.each(OTHER_STAFF)('sends $full_name away from the form', (account) => {
    const { router } = renderApp(MARQUEE_EDIT_PAGE, { session: mockSessionFor(account) })

    expect(router.state.location.pathname).not.toBe(MARQUEE_EDIT_PAGE)
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
  })
})
