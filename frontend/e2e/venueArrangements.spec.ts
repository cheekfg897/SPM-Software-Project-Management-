import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { venueRequestsPath } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/**
 * SCRUM-93: a coordinator plans one event across two venues, changes one arrangement, withdraws
 * the other, then cancels what is left, each without disturbing the rest. SCRUM-111: they cancel
 * one approved booking, with a reason, and the event's other arrangement stays as it was.
 */

// From src/mocks/handlers/bookingFixtures.ts, which Playwright can't import: it uses the `@/`
// alias. The approved event has no requests yet; venue 1 holds 200 guests and venue 2 holds 20.
const APPROVED_EVENT_REFERENCE = 'EVR-BOOK0101'
const ROOMY_VENUE_ID = 1
const TINY_VENUE_ID = 2
// The booked event: its "Main hall" is approved and its "Side room" rejected.
const BOOKED_EVENT_REFERENCE = 'EVR-BOOK0107'

async function raise(page: Page, purpose: string, venueId: number, occupancy: string) {
  const form = page
    .locator('form')
    .filter({ has: page.getByRole('button', { name: 'Request venue' }) })
  await form.getByLabel('Venue ID').fill(String(venueId))
  await form.getByLabel('Starts').fill('2026-11-10T09:00')
  await form.getByLabel('Ends').fill('2026-11-10T12:00')
  await form.getByLabel('Purpose').fill(purpose)
  await form.getByLabel('Expected occupancy').fill(occupancy)
  await form.getByRole('button', { name: 'Request venue' }).click()
  await expect(page.getByRole('listitem', { name: purpose })).toBeVisible()
}

test('a coordinator changes, withdraws and cancels an event’s venue arrangements', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.coordinator)
  await page.goto(venueRequestsPath(APPROVED_EVENT_REFERENCE))
  await expect(page.getByText('No venue requests yet.')).toBeVisible()

  await raise(page, 'Main programme', ROOMY_VENUE_ID, '80')
  await raise(page, 'Breakout', TINY_VENUE_ID, '15')

  await page.getByRole('button', { name: 'Change Breakout' }).click()
  const changeForm = page.getByRole('form', { name: 'Change Breakout' })
  await changeForm.getByLabel('Purpose').fill('Breakout workshop')
  await changeForm.getByLabel('Expected occupancy').fill('20')
  await changeForm.getByRole('button', { name: 'Save changes' }).click()
  const breakout = page.getByRole('listitem', { name: 'Breakout workshop' })
  await expect(breakout).toContainText('20 guests')

  const main = page.getByRole('listitem', { name: 'Main programme' })
  await page.getByRole('button', { name: 'Withdraw Main programme' }).click()
  await expect(main).toContainText('Withdrawn')
  await expect(breakout).toContainText('Pending')

  await page.getByRole('button', { name: 'Cancel all venue requests' }).click()
  await page.getByRole('button', { name: 'Withdraw them all' }).click()
  await expect(breakout).toContainText('Withdrawn')
  await expect(main).toContainText('Withdrawn')
})

test('a coordinator cancels one approved booking with a reason, leaving the rest', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.coordinator)
  await page.goto(venueRequestsPath(BOOKED_EVENT_REFERENCE))
  const hall = page.getByRole('listitem', { name: 'Main hall' })
  await expect(hall).toContainText('Approved')

  await page.getByRole('button', { name: 'Cancel booking Main hall' }).click()
  const form = page.getByRole('form', { name: 'Cancel booking Main hall' })
  await form.getByRole('button', { name: 'Cancel booking' }).click()
  await expect(form.getByText('A reason is required to cancel a booking.')).toBeVisible()
  await form.getByLabel('Reason for cancelling').fill('The talks moved to the side room.')
  await form.getByRole('button', { name: 'Cancel booking' }).click()

  await expect(hall).toContainText('Cancelled')
  await expect(hall.getByRole('button')).toHaveCount(0)
  await expect(page.getByRole('listitem', { name: 'Side room' })).toContainText('Rejected')
})
