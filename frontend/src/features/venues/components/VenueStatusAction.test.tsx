import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'

const VENUE_STAFF = mockSessionFor(MOCK_ACCOUNTS.venueStaff)
/** Lawn Marquee (active) and Annexe Studio (deactivated), written out. */
const MARQUEE_PAGE = '/venues/27'
const ANNEXE_PAGE = '/venues/38'
const DEACTIVATED_NOTICE = /This venue is deactivated/

/** Go to the venue list from the header and return it, once its rows are there. */
async function openTheList(user: ReturnType<typeof renderApp>['user']) {
  const nav = screen.getByRole('navigation', { name: 'Main' })
  await user.click(within(nav).getByRole('link', { name: 'Venues' }))
  return within(await screen.findByRole('list', { name: 'Venues' }))
}

/** The question that opens once "Deactivate venue" is clicked, asking why. */
const DEACTIVATE_QUESTION = 'Deactivate Lawn Marquee?'

/** Open the question on Lawn Marquee's page and return it. */
async function openTheQuestion(user: ReturnType<typeof renderApp>['user']) {
  await user.click(await screen.findByRole('button', { name: 'Deactivate venue' }))
  return within(screen.getByRole('form', { name: DEACTIVATE_QUESTION }))
}

function deactivations(requests: Request[]): Request[] {
  return requests.filter((request) => request.url.endsWith('/deactivate'))
}

describe('SCRUM-25 deactivating a venue (AC5, SCRUM-92 AC9)', () => {
  it('asks why first, and sends nothing when the venue is kept', async () => {
    const requests = recordRequests()
    const { user } = renderApp(MARQUEE_PAGE, { session: VENUE_STAFF })

    const question = await openTheQuestion(user)
    await user.click(question.getByRole('button', { name: 'Keep it active' }))

    expect(screen.queryByRole('form', { name: DEACTIVATE_QUESTION })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deactivate venue' })).toBeInTheDocument()
    expect(deactivations(requests)).toEqual([])
  })

  it('sends exactly the category and the note, then the venue says so and leaves the list', async () => {
    const requests = recordRequests()
    const { user } = renderApp(MARQUEE_PAGE, { session: VENUE_STAFF })

    const question = await openTheQuestion(user)
    await user.selectOptions(question.getByLabelText('Why'), 'Renovation')
    await user.type(question.getByLabelText('Note'), 'Roof works until March')
    await user.click(question.getByRole('button', { name: 'Deactivate' }))

    expect(await screen.findByText(DEACTIVATED_NOTICE)).toBeInTheDocument()
    const [sent] = deactivations(requests)
    expect(new URL(sent?.url ?? '').pathname).toBe('/api/venues/27/deactivate')
    await expect(sent?.json()).resolves.toEqual({
      category: 'renovation',
      reason: 'Roof works until March',
    })
    expect(screen.getByRole('button', { name: 'Reactivate venue' })).toBeInTheDocument()
    const list = await openTheList(user)
    expect(list.getByRole('link', { name: /Marina Hall/ })).toBeInTheDocument()
    expect(list.queryByRole('link', { name: /Lawn Marquee/ })).not.toBeInTheDocument()
  })

  it('offers every reason the backend accepts, in its order, and none chosen to start', async () => {
    const { user } = renderApp(MARQUEE_PAGE, { session: VENUE_STAFF })

    const why = (await openTheQuestion(user)).getByLabelText('Why')
    const options = within(why).getAllByRole('option')

    expect(why).toHaveValue('')
    expect(options.map((option) => [option.getAttribute('value'), option.textContent])).toEqual([
      ['', 'Choose one'],
      ['maintenance', 'Maintenance'],
      ['equipment_failure', 'Equipment failure'],
      ['renovation', 'Renovation'],
      ['safety_concern', 'Safety concern'],
      ['other', 'Other'],
    ])
  })

  it('says what deactivating does to bookings, before and while asking', async () => {
    const { user } = renderApp(MARQUEE_PAGE, { session: VENUE_STAFF })

    const section = await screen.findByRole('region', { name: 'Deactivate venue' })
    expect(section).toHaveTextContent(
      'It leaves the venue list and venue search. Bookings already made for it keep it, but each one that has not ended is flagged as needing an alternative venue.',
    )

    await openTheQuestion(user)
    expect(screen.getByRole('form', { name: DEACTIVATE_QUESTION })).toHaveTextContent(
      'Every booking and request here that has not ended is flagged "Needs Alternative Venue". A confirmed event goes back to Approved, and its coordinator is told why, with your note. Reactivating the venue clears the flags, but those events stay Approved.',
    )
  })

  it('shows the backend messages under the fields they are for, as sent', async () => {
    server.use(
      http.post('/api/venues/27/deactivate', () =>
        HttpResponse.json(
          {
            error: 'validation_error',
            message: 'Invalid request.',
            details: { category: ['Pick a reason first.'], reason: ['Say a little more.'] },
          },
          { status: 400 },
        ),
      ),
    )
    const { user } = renderApp(MARQUEE_PAGE, { session: VENUE_STAFF })

    const question = await openTheQuestion(user)
    await user.click(question.getByRole('button', { name: 'Deactivate' }))

    expect(await question.findByText('Pick a reason first.')).toBeInTheDocument()
    expect(question.getByLabelText('Why')).toHaveAccessibleDescription('Pick a reason first.')
    expect(question.getByLabelText('Note')).toHaveAccessibleDescription('Say a little more.')
    expect(screen.queryByText(DEACTIVATED_NOTICE)).not.toBeInTheDocument()
  })

  it('shows the backend message when it is refused', async () => {
    server.use(
      http.post('/api/venues/27/deactivate', () =>
        HttpResponse.json(
          { error: 'conflict', message: 'This venue cannot be deactivated now.' },
          { status: 409 },
        ),
      ),
    )
    const { user } = renderApp(MARQUEE_PAGE, { session: VENUE_STAFF })

    const question = await openTheQuestion(user)
    await user.selectOptions(question.getByLabelText('Why'), 'Maintenance')
    await user.type(question.getByLabelText('Note'), 'Lift broken')
    await user.click(question.getByRole('button', { name: 'Deactivate' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This venue cannot be deactivated now.',
    )
    expect(screen.queryByText(DEACTIVATED_NOTICE)).not.toBeInTheDocument()
  })
})

describe('SCRUM-25 reactivating a venue (AC6)', () => {
  it('reactivates a deactivated venue, which comes back to the list', async () => {
    const requests = recordRequests()
    const { user } = renderApp(ANNEXE_PAGE, { session: VENUE_STAFF })
    await screen.findByText(DEACTIVATED_NOTICE)

    await user.click(screen.getByRole('button', { name: 'Reactivate venue' }))

    expect(await screen.findByRole('button', { name: 'Deactivate venue' })).toBeInTheDocument()
    expect(screen.queryByText(DEACTIVATED_NOTICE)).not.toBeInTheDocument()
    const sent = requests.find((request) => request.method === 'POST')
    expect(new URL(sent?.url ?? '').pathname).toBe('/api/venues/38/reactivate')
    const list = await openTheList(user)
    expect(list.getByRole('link', { name: /Annexe Studio/ })).toBeInTheDocument()
  })
})

describe('SCRUM-25 only Venue Staff deactivate or reactivate (AC4)', () => {
  it.each([MOCK_ACCOUNTS.coordinator, MOCK_ACCOUNTS.lead, MOCK_ACCOUNTS.technicalSupport])(
    'offers $full_name neither',
    async (account) => {
      renderApp(ANNEXE_PAGE, { session: mockSessionFor(account) })
      await screen.findByText(DEACTIVATED_NOTICE)

      expect(screen.queryByRole('button', { name: 'Reactivate venue' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Deactivate venue' })).not.toBeInTheDocument()
    },
  )
})
