import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { markNotificationRead } from '@/features/notifications/api'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'
import { sendRequestsAs } from '@/test/sendRequestsAs'

const session = mockSessionFor(MOCK_ACCOUNTS.attendee)

// The attendee has two unread notifications and one read (mocks/handlers/notifications.ts).
const BELL_WITH_TWO = 'Notifications, 2 unread'

function bellInHeader(name: string | RegExp) {
  return within(screen.getByRole('banner')).findByRole('link', { name })
}

describe('SCRUM-28 notification bell', () => {
  it('links to the notifications page and says how many are unread', async () => {
    renderApp(ROUTES.HOME, { session })

    const bell = await bellInHeader(BELL_WITH_TWO)

    expect(bell).toHaveAttribute('href', ROUTES.NOTIFICATIONS)
    expect(bell).toHaveTextContent('2')
  })

  it('opens the notifications page when clicked', async () => {
    const { user, router } = renderApp(ROUTES.HOME, { session })

    await user.click(await bellInHeader(BELL_WITH_TWO))

    expect(router.state.location.pathname).toBe(ROUTES.NOTIFICATIONS)
  })

  it('shows no badge at all when nothing is unread', async () => {
    server.use(
      http.get('/api/notifications/unread-count', () => HttpResponse.json({ unread_count: 0 })),
    )
    renderApp(ROUTES.HOME, { session })

    const bell = await bellInHeader('Notifications')

    expect(bell.textContent).toBe('')
  })

  it('shows no bell and sends no request to a visitor', async () => {
    const requests = recordRequests()
    renderApp(ROUTES.HOME)

    await screen.findByRole('link', { name: 'Log in' })
    expect(screen.queryByRole('link', { name: /^Notifications/ })).not.toBeInTheDocument()
    expect(requests.filter((request) => request.url.includes('/api/notifications'))).toEqual([])
  })

  it('counts down by one when an unread notification is marked read', async () => {
    const { user } = renderApp(ROUTES.NOTIFICATIONS, { session })
    await bellInHeader(BELL_WITH_TWO)
    const row = (await screen.findByText('A new event request was submitted.')).closest('li')!

    await user.click(within(row).getByRole('button', { name: 'Mark read' }))

    expect(await bellInHeader('Notifications, 1 unread')).toBeInTheDocument()
  })

  it('does not count down twice for one the backend already has as read', async () => {
    const { user } = renderApp(ROUTES.NOTIFICATIONS, { session })
    await bellInHeader(BELL_WITH_TWO)
    const row = (await screen.findByText('A new event request was submitted.')).closest('li')!
    sendRequestsAs(session.accessToken)
    await markNotificationRead(1)

    await user.click(within(row).getByRole('button', { name: 'Mark read' }))

    // Notification 2 is still unread, so the backend's count is 1, not 0.
    await waitFor(() => expect(within(row).queryByText('Unread')).not.toBeInTheDocument())
    expect(await bellInHeader('Notifications, 1 unread')).toBeInTheDocument()
  })
})
