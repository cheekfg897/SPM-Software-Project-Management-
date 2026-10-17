import { expect, test } from '@playwright/test'

import { ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/**
 * SCRUM-6 AC3: once signed in, the front page and the logo lead to the user's own home, and
 * logging out still leaves them on the front page.
 */

test('a signed-in organiser opening the site, or clicking the logo, lands on their home', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.organiser)

  await page.goto(ROUTES.HOME)
  await expect(page).toHaveURL(ROUTES.ORGANISER_HOME)

  await page.goto(ROUTES.EVENTS)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await page.getByRole('banner').getByRole('link', { name: 'ConnectSphere' }).click()
  await expect(page).toHaveURL(ROUTES.ORGANISER_HOME)
})

test('staff logging out from their home land on the front page, signed out', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.coordinator)
  await page.goto(ROUTES.STAFF_HOME)
  const header = page.getByRole('banner')

  await header.getByRole('button', { name: 'Log out' }).click()

  await expect(page).toHaveURL(ROUTES.HOME)
  await expect(header.getByRole('link', { name: 'Log in' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Sign up' }).first()).toBeVisible()
})
