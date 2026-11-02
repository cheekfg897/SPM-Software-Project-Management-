import { expect, test } from '@playwright/test'

import { ROUTES, venueRequestsPath } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/**
 * SCRUM-70: Venue Staff reject a request suggesting another venue and period, and a coordinator
 * raises a new request from a suggestion, changing it before sending.
 */

// From src/mocks/handlers/bookingFixtures.ts, which Playwright can't import: it uses the `@/`
// alias. "Breakout room" waits for a decision. The multi-venue event's "Main programme" was
// rejected with the Garden Pavilion (venue 33) suggested for 26 Nov, 1 pm to 5 pm.
const BREAKOUT_ROOM = 'Breakout room'
const MULTI_VENUE_EVENT_REFERENCE = 'EVR-BOOK0106'
const REJECTED_PURPOSE = 'Main programme'

test('Venue Staff reject a request and suggest an alternative', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.venueStaff)
  await page.goto(ROUTES.BOOKING_DECISIONS)

  const queue = page.getByRole('region', { name: 'Waiting for a decision' })
  const breakout = queue.getByRole('article', { name: BREAKOUT_ROOM })
  await breakout.getByLabel(`Reason for ${BREAKOUT_ROOM}`).fill('Closed for repairs')
  await breakout.getByLabel(`Suggested venue ID for ${BREAKOUT_ROOM}`).fill('33')
  await breakout.getByLabel(`Suggested start for ${BREAKOUT_ROOM}`).fill('2026-11-21T09:00')
  await breakout.getByLabel(`Suggested end for ${BREAKOUT_ROOM}`).fill('2026-11-21T12:00')
  await breakout.getByRole('button', { name: `Reject ${BREAKOUT_ROOM}` }).click()

  await expect(breakout).toHaveCount(0)
  await expect(queue.getByRole('article', { name: 'Main hall' })).toBeVisible()
})

test('a coordinator raises a new request from a suggested alternative', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.coordinator)
  await page.goto(venueRequestsPath(MULTI_VENUE_EVENT_REFERENCE))

  const rejected = page.getByRole('listitem', { name: REJECTED_PURPOSE, exact: true })
  await expect(rejected).toContainText('Reason: Hall closed for repairs')
  await expect(rejected).toContainText('Venue Staff suggest instead: Venue 33 · 26 Nov')

  await rejected
    .getByRole('link', { name: `Raise a request from the suggestion for ${REJECTED_PURPOSE}` })
    .click()
  await expect(page.getByText(`Starting from Venue Staff's suggestion`)).toBeVisible()
  await expect(page.getByLabel('Venue ID')).toHaveValue('33')
  await expect(page.getByLabel('Starts')).toHaveValue('2026-11-26T13:00')
  await page.getByLabel('Purpose').fill('Main programme, moved')
  await page.getByRole('button', { name: 'Request venue' }).click()

  await expect(page.getByRole('listitem', { name: 'Main programme, moved' })).toContainText(
    'Pending',
  )
  await expect(rejected).toContainText('Rejected')
})
