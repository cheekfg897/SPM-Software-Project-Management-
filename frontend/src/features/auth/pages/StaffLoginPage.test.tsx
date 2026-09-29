import { screen } from '@testing-library/react'

import { ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS } from '@/mocks/handlers/auth'
import { renderApp } from '@/test/render'

import { logInThroughForm } from '../test/logInThroughForm'

describe('SCRUM-6 staff log in', () => {
  it('logs a coordinator in and takes them to the staff home', async () => {
    const { user, router } = renderApp(ROUTES.STAFF_LOGIN)
    const { coordinator } = MOCK_ACCOUNTS

    await logInThroughForm(user, coordinator)

    expect(await screen.findByText(`Welcome back, ${coordinator.full_name}.`)).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(ROUTES.STAFF_HOME)
  })

  it('offers no sign-up, because staff accounts are provided (ADR-0023)', () => {
    renderApp(ROUTES.STAFF_LOGIN)

    expect(screen.queryByRole('link', { name: /create an account/i })).not.toBeInTheDocument()
    expect(screen.getByText(/accounts are set up by ConnectSphere/i)).toBeInTheDocument()
  })
})
