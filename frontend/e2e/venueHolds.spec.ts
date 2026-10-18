import { expect, test } from '@playwright/test'

import { ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/**
 * SCRUM-75: Venue Staff hold a venue for one of a multi-venue event's requests, move the hold's
 * expiry, then give their final approval, and the request leaves the queue. The Breakout room
 * request is one of two venues for its event (src/mocks/handlers/bookingFixtures.ts).
 */

const BREAKOUT_ROOM = 'Breakout room'

test('Venue Staff hold a venue, move the expiry, then give final approval', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.venueStaff)
  await page.goto(ROUTES.BOOKING_DECISIONS)

  const breakout = page.getByRole('article', { name: BREAKOUT_ROOM })
  await expect(breakout.getByText('Pending')).toBeVisible()

  await breakout.getByLabel(`Hold expiry for ${BREAKOUT_ROOM}`).fill('2026-11-15T17:00')
  await breakout.getByRole('button', { name: `Place hold for ${BREAKOUT_ROOM}` }).click()
  await expect(breakout.getByText('On hold')).toBeVisible()
  await expect(breakout.getByText('Hold expiry: 15 Nov, 5:00 pm')).toBeVisible()

  await breakout.getByLabel(`Hold expiry for ${BREAKOUT_ROOM}`).fill('2026-11-18T12:00')
  await breakout.getByRole('button', { name: `Change expiry for ${BREAKOUT_ROOM}` }).click()
  await expect(breakout.getByText('Hold expiry: 18 Nov, 12:00 pm')).toBeVisible()

  await breakout.getByRole('button', { name: `Approve ${BREAKOUT_ROOM}` }).click()
  await expect(breakout).toHaveCount(0)
  await expect(page.getByRole('article', { name: 'Main hall' })).toBeVisible()
})
