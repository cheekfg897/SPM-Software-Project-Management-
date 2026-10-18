import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

import { bodyOf, period, periodCount, retype } from '../test/venueFormSteps'

const VENUE_STAFF = mockSessionFor(MOCK_ACCOUNTS.venueStaff)
const COORDINATOR = mockSessionFor(MOCK_ACCOUNTS.coordinator)
/** The id the venue mock gives the first venue it creates. */
const FIRST_NEW_VENUE_PATH = '/venues/900'

function openNewVenueForm() {
  return renderApp(ROUTES.NEW_VENUE, { session: VENUE_STAFF })
}

async function fillInTheRequiredFields(user: ReturnType<typeof renderApp>['user']) {
  await user.type(screen.getByLabelText('Name'), 'Skyline Room')
  await user.type(screen.getByLabelText('Location'), 'Level 9, Tower Block')
  await user.type(screen.getByLabelText('Capacity'), '64')
}

describe('SCRUM-25 adding a venue', () => {
  it('sends what Venue Staff filled in and opens the new venue', async () => {
    const requests = recordRequests()
    const { user, router } = openNewVenueForm()

    await fillInTheRequiredFields(user)
    await user.click(screen.getByRole('checkbox', { name: 'Theatre' }))
    await user.click(screen.getByRole('checkbox', { name: 'Boardroom' }))
    await user.type(screen.getByLabelText('Facilities'), 'Projector{Enter}{Enter}Stage')
    await user.type(screen.getByLabelText('Accessibility features'), 'Hearing loop')
    await user.type(screen.getByLabelText('Setup time (minutes)'), '20')
    await user.type(screen.getByLabelText('Turnaround time (minutes)'), '0')
    await user.click(screen.getByRole('button', { name: 'Add venue' }))

    await waitFor(() => expect(router.state.location.pathname).toBe(FIRST_NEW_VENUE_PATH))
    const sent = await bodyOf(requests, 'POST')
    expect(sent).toMatchObject({
      name: 'Skyline Room',
      location: 'Level 9, Tower Block',
      capacity: 64,
      supported_layouts: ['theatre', 'boardroom'],
      facilities: ['Projector', 'Stage'],
      accessibility_features: ['Hearing loop'],
      setup_minutes: 20,
      turnaround_minutes: 0,
    })
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Skyline Room' }),
    ).toBeInTheDocument()
  })

  it('starts with the standard hours, every day 09:00 to 18:00, and sends them (ADR-0067)', async () => {
    const requests = recordRequests()
    const { user, router } = openNewVenueForm()

    expect(periodCount()).toBe(7)
    expect(period(7).getByLabelText('Opens on')).toHaveValue('sunday')
    expect(period(7).getByLabelText('Opens at')).toHaveValue('09:00')
    expect(period(7).getByLabelText('Closes on')).toHaveValue('sunday')
    expect(period(7).getByLabelText('Closes at')).toHaveValue('18:00')
    await fillInTheRequiredFields(user)
    await user.click(screen.getByRole('button', { name: 'Add venue' }))

    await waitFor(() => expect(router.state.location.pathname).toBe(FIRST_NEW_VENUE_PATH))
    const sent = await bodyOf(requests, 'POST')
    expect(sent).toMatchObject({
      opening_hours: expect.arrayContaining([
        { open: { day: 'monday', time: '09:00' }, close: { day: 'monday', time: '18:00' } },
      ]) as unknown,
    })
    expect(sent).not.toHaveProperty('setup_minutes')
    expect(sent).not.toHaveProperty('turnaround_minutes')
  })

  it('says that empty times take the standard time (SCRUM-67 AC2)', () => {
    openNewVenueForm()

    expect(screen.getByLabelText('Setup time (minutes)')).toHaveAccessibleDescription(
      'Leave empty for the standard time.',
    )
  })

  it('shows the backend messages under the fields it refused and moves to the first', async () => {
    const { user } = openNewVenueForm()

    await user.click(screen.getByRole('button', { name: 'Add venue' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid request.')
    expect(screen.getByLabelText('Name')).toHaveAccessibleDescription('Must not be blank.')
    expect(screen.getByLabelText('Location')).toHaveAccessibleDescription('Must not be blank.')
    expect(screen.getByLabelText('Capacity')).toHaveAccessibleDescription('Field may not be null.')
    expect(screen.getByLabelText('Name')).toHaveFocus()
  })

  it('names the item the backend refused in a list', async () => {
    const { user } = openNewVenueForm()

    await fillInTheRequiredFields(user)
    await user.type(screen.getByLabelText('Facilities'), 'Stage{Enter}Lights, camera')
    await user.click(screen.getByRole('button', { name: 'Add venue' }))

    expect(await screen.findByText('Item 2: Items cannot contain ",".')).toBeInTheDocument()
    expect(screen.getByLabelText('Facilities')).toBeInvalid()
  })

  it('shows the backend messages for the layouts under them, as sent', async () => {
    server.use(
      http.post('/api/venues', () =>
        HttpResponse.json(
          {
            error: 'validation_error',
            message: 'Invalid request.',
            details: { supported_layouts: ['Pick fewer layouts.'] },
          },
          { status: 400 },
        ),
      ),
    )
    const { user } = openNewVenueForm()

    await fillInTheRequiredFields(user)
    await user.click(screen.getByRole('button', { name: 'Add venue' }))

    const layouts = await screen.findByRole('group', { name: 'Layouts it supports' })
    await waitFor(() => expect(layouts).toHaveAccessibleDescription('Pick fewer layouts.'))
    expect(screen.getByRole('checkbox', { name: 'Theatre' })).toBeInvalid()
  })
})

describe('SCRUM-25 opening hours on the venue form (ADR-0008)', () => {
  it('removes a period and adds one, sending exactly the periods shown', async () => {
    const requests = recordRequests()
    const { user, router } = openNewVenueForm()

    await fillInTheRequiredFields(user)
    for (let removed = 0; removed < 6; removed += 1) {
      await user.click(screen.getByRole('button', { name: 'Remove period 1' }))
    }
    await user.click(screen.getByRole('button', { name: 'Add a period' }))
    await user.selectOptions(period(2).getByLabelText('Opens on'), 'friday')
    await retype(user, period(2).getByLabelText('Opens at'), '18:00')
    await user.selectOptions(period(2).getByLabelText('Closes on'), 'saturday')
    await retype(user, period(2).getByLabelText('Closes at'), '02:00')
    await user.click(screen.getByRole('button', { name: 'Add venue' }))

    await waitFor(() => expect(router.state.location.pathname).toBe(FIRST_NEW_VENUE_PATH))
    expect(await bodyOf(requests, 'POST')).toMatchObject({
      opening_hours: [
        { open: { day: 'sunday', time: '09:00' }, close: { day: 'sunday', time: '18:00' } },
        { open: { day: 'friday', time: '18:00' }, close: { day: 'saturday', time: '02:00' } },
      ],
    })
  })

  it('removes only the added period asked for when several have been added', async () => {
    const { user } = openNewVenueForm()

    for (let removed = 0; removed < 7; removed += 1) {
      await user.click(screen.getByRole('button', { name: 'Remove period 1' }))
    }
    await user.click(screen.getByRole('button', { name: 'Add a period' }))
    await user.click(screen.getByRole('button', { name: 'Add a period' }))
    await user.selectOptions(period(2).getByLabelText('Opens on'), 'thursday')
    await user.click(screen.getByRole('button', { name: 'Remove period 1' }))

    expect(periodCount()).toBe(1)
    expect(period(1).getByLabelText('Opens on')).toHaveValue('thursday')
  })

  it('sends no periods at all once every one is removed, and says that means closed', async () => {
    const requests = recordRequests()
    const { user, router } = openNewVenueForm()

    await fillInTheRequiredFields(user)
    for (let removed = 0; removed < 7; removed += 1) {
      await user.click(screen.getByRole('button', { name: 'Remove period 1' }))
    }
    expect(screen.getByText('With no periods, the venue is closed all week.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add venue' }))

    await waitFor(() => expect(router.state.location.pathname).toBe(FIRST_NEW_VENUE_PATH))
    expect(await bodyOf(requests, 'POST')).toMatchObject({ opening_hours: [] })
  })

  it('shows a period rule under the close time and an overlap under its period', async () => {
    const { user } = openNewVenueForm()

    await fillInTheRequiredFields(user)
    await retype(user, period(1).getByLabelText('Closes at'), '08:00')
    await user.selectOptions(period(3).getByLabelText('Opens on'), 'tuesday')
    await user.selectOptions(period(3).getByLabelText('Closes on'), 'tuesday')
    await user.click(screen.getByRole('button', { name: 'Add venue' }))

    expect(await screen.findByText(/^Close time must be after open time\./)).toBeInTheDocument()
    expect(period(1).getByLabelText('Closes at')).toBeInvalid()
    await retype(user, period(1).getByLabelText('Closes at'), '18:00')
    await user.click(screen.getByRole('button', { name: 'Add venue' }))
    expect(await period(3).findByText('Overlaps opening period 1.')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Period 3' })).toHaveAccessibleDescription(
      'Overlaps opening period 1.',
    )
  })

  it('shows an empty time as the backend refuses it', async () => {
    const { user } = openNewVenueForm()

    await fillInTheRequiredFields(user)
    await user.clear(period(2).getByLabelText('Opens at'))
    await user.click(screen.getByRole('button', { name: 'Add venue' }))

    expect(await period(2).findByText('Not a valid time.')).toBeInTheDocument()
    expect(period(2).getByLabelText('Opens at')).toHaveFocus()
  })
})

describe('SCRUM-25 who may add a venue', () => {
  it('shows Venue Staff the way to add one from the list', async () => {
    const { user, router } = renderApp(ROUTES.VENUES, { session: VENUE_STAFF })

    await user.click(await screen.findByRole('link', { name: 'Add a venue' }))

    expect(router.state.location.pathname).toBe(ROUTES.NEW_VENUE)
  })

  it('shows other staff no way to add one', async () => {
    renderApp(ROUTES.VENUES, { session: COORDINATOR })
    await screen.findByRole('link', { name: /Marina Hall/ })

    expect(screen.queryByRole('link', { name: 'Add a venue' })).not.toBeInTheDocument()
  })

  it.each([MOCK_ACCOUNTS.coordinator, MOCK_ACCOUNTS.lead, MOCK_ACCOUNTS.technicalSupport])(
    'sends $full_name away from the form to their home',
    (account) => {
      const { router } = renderApp(ROUTES.NEW_VENUE, { session: mockSessionFor(account) })

      expect(router.state.location.pathname).not.toBe(ROUTES.NEW_VENUE)
      expect(screen.queryByRole('button', { name: 'Add venue' })).not.toBeInTheDocument()
    },
  )
})
