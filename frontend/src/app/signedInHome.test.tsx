import { act, screen, waitFor, within } from '@testing-library/react'

import { ROUTES } from '@/config/routes'
import { logInThroughForm } from '@/features/auth/test/logInThroughForm'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { renderApp } from '@/test/render'

/**
 * SCRUM-6 AC3: a signed-in user's landing view is their role's home, so opening the site's
 * front page, or clicking the logo, takes them there instead of the visitors' page with its
 * sign-up buttons. Visitors still see that page.
 */

// The landing page draws a canvas, which jsdom can't; nothing here looks at the drawing.
vi.mock('@/features/landing/blackHole/renderer', () => ({ drawScene: vi.fn(), fitCanvas: vi.fn() }))

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => null)
})

afterEach(() => vi.restoreAllMocks())

/** Each role's home, written out rather than read from homeFor, so a wrong mapping shows. */
const HOMES: { account: MockAccount; home: string }[] = [
  { account: MOCK_ACCOUNTS.attendee, home: '/my-events' },
  { account: MOCK_ACCOUNTS.organiser, home: '/organiser' },
  { account: MOCK_ACCOUNTS.coordinator, home: '/staff' },
  { account: MOCK_ACCOUNTS.lead, home: '/staff/queue' },
  { account: MOCK_ACCOUNTS.venueStaff, home: '/staff' },
  { account: MOCK_ACCOUNTS.technicalSupport, home: '/staff' },
]

function logo() {
  return within(screen.getByRole('banner')).getByRole('link', { name: 'ConnectSphere' })
}

describe('SCRUM-6 a signed-in user’s home', () => {
  it.each(HOMES)('takes $account.role from the front page to $home', async ({ account, home }) => {
    const { router } = renderApp(ROUTES.HOME, { session: mockSessionFor(account) })

    await waitFor(() => expect(router.state.location.pathname).toBe(home))
    expect(screen.queryByRole('link', { name: 'Sign up' })).not.toBeInTheDocument()
  })

  it('takes a signed-in organiser home when they click the logo', async () => {
    const { user, router } = renderApp(ROUTES.EVENTS, {
      session: mockSessionFor(MOCK_ACCOUNTS.organiser),
    })

    await user.click(logo())

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.ORGANISER_HOME))
  })

  it('replaces the front page in the history, so Back does not bounce them home again', async () => {
    const { router } = renderApp(ROUTES.HOME, {
      session: mockSessionFor(MOCK_ACCOUNTS.venueStaff),
    })

    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.STAFF_HOME))
    expect(router.state.historyAction).toBe('REPLACE')
  })

  it('still shows a visitor the front page, with its sign-up buttons', () => {
    const { router } = renderApp(ROUTES.HOME)

    expect(router.state.location.pathname).toBe(ROUTES.HOME)
    expect(
      within(screen.getByRole('banner')).getByRole('link', { name: 'Sign up' }),
    ).toBeInTheDocument()
    expect(logo()).toHaveAttribute('href', ROUTES.HOME)
  })

  it('forgets what the last user read, so the next one on this device never sees it', async () => {
    // Venue requests are cached by event, not by viewer: only logging out clears them.
    const venueRequests = '/events/EVR-BOOK0104/venue-requests'
    const { user, router } = renderApp(venueRequests, {
      session: mockSessionFor(MOCK_ACCOUNTS.coordinator),
    })
    await screen.findByRole('listitem', { name: 'Main hall' })
    await user.click(within(screen.getByRole('banner')).getByRole('button', { name: 'Log out' }))
    await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.HOME))

    await act(() =>
      router.navigate(`${ROUTES.STAFF_LOGIN}?next=${encodeURIComponent(venueRequests)}`),
    )
    await screen.findByLabelText('Email')
    await logInThroughForm(user, MOCK_ACCOUNTS.idleCoordinator)

    expect(await screen.findByRole('alert')).toHaveTextContent('Event request not found.')
    expect(screen.queryByRole('listitem', { name: 'Main hall' })).not.toBeInTheDocument()
  })

  it.each([
    ['an attendee', ROUTES.MY_EVENTS, MOCK_ACCOUNTS.attendee],
    ['a coordinator', ROUTES.STAFF_HOME, MOCK_ACCOUNTS.coordinator],
  ])('logs %s out to the front page, not back to their home', async (_who, path, account) => {
    const { user, router, store } = renderApp(path, { session: mockSessionFor(account) })
    const header = within(screen.getByRole('banner'))

    await user.click(header.getByRole('button', { name: 'Log out' }))

    await waitFor(() => expect(header.getByRole('link', { name: 'Log in' })).toBeInTheDocument())
    expect(router.state.location.pathname).toBe(ROUTES.HOME)
    expect(store.getState().session.accessToken).toBeNull()
  })
})
