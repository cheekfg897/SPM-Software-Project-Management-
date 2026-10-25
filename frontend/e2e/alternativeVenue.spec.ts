import { expect, test } from '@playwright/test'

import { ROUTES, venueRequestsPath } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/**
 * SCRUM-92: a coordinator sees why a booked venue needs replacing, finds another venue for the
 * same period and raises a replacement linked to the original booking, which keeps its period.
 */

// From src/mocks/handlers/bookingFixtures.ts, which Playwright can't import: it uses the `@/`
// alias. The booked event's approved "Main hall" (26 Nov, 1 pm to 5 pm, for 10) is flagged
// because its venue is blocked for roof repairs.
const BOOKED_EVENT_REFERENCE = 'EVR-BOOK0107'
const FLAGGED_PURPOSE = 'Main hall'

test('a coordinator replaces a booked venue that became unavailable', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.coordinator)
  await page.goto(venueRequestsPath(BOOKED_EVENT_REFERENCE))

  const original = page.getByRole('listitem', { name: FLAGGED_PURPOSE, exact: true })
  await expect(original).toContainText('Needs an alternative venue')
  await expect(original).toContainText('Maintenance: Roof repairs.')
  await expect(original).toContainText('Approved')

  await original.getByRole('link', { name: `Find another venue for ${FLAGGED_PURPOSE}` }).click()
  await expect(page).toHaveURL(new RegExp(`^[^?]*${ROUTES.VENUE_SEARCH}\\?`))
  await expect(page.getByLabel('Date', { exact: true })).toHaveValue('2026-11-26')
  await expect(page.getByLabel('Start time')).toHaveValue('13:00')
  await expect(page.getByLabel('Minimum capacity')).toHaveValue('10')

  await page.getByRole('link', { name: 'Request Boardroom Two as the replacement' }).click()
  await expect(page.getByText(`Replacing ${FLAGGED_PURPOSE},`)).toBeVisible()
  await expect(page.getByLabel('Venue ID')).toHaveValue('2')
  await expect(page.getByLabel('Starts')).toHaveValue('2026-11-26T13:00')
  // The replacement keeps the flagged booking's date and times (Product Owner 25 Oct).
  await expect(page.getByLabel('Starts')).not.toBeEditable()
  await expect(page.getByLabel('Ends')).not.toBeEditable()
  await page.getByLabel('Purpose').fill('Main hall, moved')
  await page.getByRole('button', { name: 'Request venue' }).click()

  const replacement = page.getByRole('listitem', { name: 'Main hall, moved' })
  await expect(replacement).toContainText(`Replaces ${FLAGGED_PURPOSE}`)
  await expect(replacement).toContainText('Pending')
  await expect(original).toContainText('Needs an alternative venue')
})
