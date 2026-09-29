import { screen } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'

/** Type the details into the log-in form and submit it, as a user would. */
export async function logInThroughForm(
  user: UserEvent,
  credentials: { email: string; password: string },
) {
  await user.type(screen.getByLabelText('Email'), credentials.email)
  await user.type(screen.getByLabelText('Password'), credentials.password)
  await user.click(screen.getByRole('button', { name: 'Log in' }))
}
