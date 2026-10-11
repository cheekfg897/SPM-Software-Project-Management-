import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { errorResponse } from '@/mocks/responses'
import { server } from '@/mocks/server'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { markNotificationRead } from '../api'
import { findRow } from '../test/findRow'

const session = mockSessionFor(MOCK_ACCOUNTS.attendee)

// The attendee's seeded notifications, newest first (mocks/handlers/notifications.ts).
const UNREAD_MESSAGE = 'A new event request was submitted.'
const READ_MESSAGE = 'You have been assigned to coordinate this event.'

describe('SCRUM-28 notifications page', () => {
  it('sends a visitor to log in, and asks for nothing', async () => {
    const requests = recordRequests()
    const { router } = renderApp(ROUTES.NOTIFICATIONS)

    await screen.findByRole('heading', { name: 'Log in' })
    expect(router.state.location.search).toBe('?next=%2Fnotifications')
    expect(requests.filter((request) => request.url.includes('/api/notifications'))).toEqual([])
  })

  it('shows each notification as the backend sent it', async () => {
    renderApp(ROUTES.NOTIFICATIONS, { session })

    const row = await findRow(UNREAD_MESSAGE)
    expect(within(row).getByText('5 Oct, 9:00 am')).toBeInTheDocument()
    expect(within(row).getByText('Doors open at 7pm.')).toBeInTheDocument()
    expect(within(row).getByRole('link', { name: 'Jazz by the Bay' })).toHaveAttribute(
      'href',
      '/events/EVR-MOCK0001',
    )
  })

  it('shows nothing extra for a notification without a detail', async () => {
    renderApp(ROUTES.NOTIFICATIONS, { session })

    const row = await findRow(READ_MESSAGE)
    expect(row.textContent).toBe(`${READ_MESSAGE}Board Game Social3 Oct, 11:00 am`)
  })

  it('tells unread from read, and only offers to mark an unread one', async () => {
    renderApp(ROUTES.NOTIFICATIONS, { session })

    const unread = await findRow(UNREAD_MESSAGE)
    const read = await findRow(READ_MESSAGE)
    expect(within(unread).getByText('Unread')).toBeInTheDocument()
    expect(within(unread).getByRole('button', { name: 'Mark read' })).toBeEnabled()
    expect(within(read).queryByText('Unread')).not.toBeInTheDocument()
    expect(within(read).queryByRole('button', { name: 'Mark read' })).not.toBeInTheDocument()
  })

  it('marks one read, then asks for the list again', async () => {
    const { user } = renderApp(ROUTES.NOTIFICATIONS, { session })
    const row = await findRow(UNREAD_MESSAGE)
    const requests = recordRequests()

    await user.click(within(row).getByRole('button', { name: 'Mark read' }))

    await waitFor(() => expect(within(row).queryByText('Unread')).not.toBeInTheDocument())
    expect(within(row).queryByRole('button', { name: 'Mark read' })).not.toBeInTheDocument()
    const sent = requests.map((request) => `${request.method} ${new URL(request.url).pathname}`)
    expect(sent).toContain('POST /api/notifications/1/read')
    expect(sent).toContain('GET /api/notifications')
  })

  it('is harmless to mark one the backend already has as read', async () => {
    const { user } = renderApp(ROUTES.NOTIFICATIONS, { session })
    const row = await findRow(UNREAD_MESSAGE)
    sendRequestsAs(session.accessToken)
    await markNotificationRead(1)

    await user.click(within(row).getByRole('button', { name: 'Mark read' }))

    await waitFor(() => expect(within(row).queryByText('Unread')).not.toBeInTheDocument())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it("shows the backend's message when marking one read fails", async () => {
    server.use(
      http.post('/api/notifications/:id/read', () =>
        errorResponse(404, 'not_found', 'Notification not found.'),
      ),
    )
    const { user } = renderApp(ROUTES.NOTIFICATIONS, { session })
    const row = await findRow(UNREAD_MESSAGE)

    await user.click(within(row).getByRole('button', { name: 'Mark read' }))

    expect(await within(row).findByRole('alert')).toHaveTextContent('Notification not found.')
    expect(within(row).getByText('Unread')).toBeInTheDocument()
  })

  it('says what is loading while it waits', async () => {
    server.use(http.get('/api/notifications', () => new Promise(() => undefined)))
    renderApp(ROUTES.NOTIFICATIONS, { session })

    expect(await screen.findByRole('status')).toHaveTextContent('Loading notifications')
  })

  it('shows an empty state, not a spinner, when there are none', async () => {
    server.use(http.get('/api/notifications', () => HttpResponse.json({ notifications: [] })))
    renderApp(ROUTES.NOTIFICATIONS, { session })

    expect(await screen.findByText('You have no notifications yet.')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it("shows the backend's message when the list can't be loaded", async () => {
    server.use(
      http.get('/api/notifications', () =>
        errorResponse(500, 'internal_error', 'Something went wrong.'),
      ),
    )
    renderApp(ROUTES.NOTIFICATIONS, { session })

    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong.')
  })
})
