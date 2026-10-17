import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'
import type { MockAccount } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/** SCRUM-26 and SCRUM-34: staff read a venue's availability; Venue Staff block it. */

/**
 * Open Marina Hall from the header's Venues link and show 10 and 11 Nov, moving within the app
 * (a reload resets the mock backend) and waiting for each step to show.
 */
async function openMarinaHallOnTenAndElevenNovember(page: Page, account: MockAccount) {
  await signInAs(page, account)
  await page.goto(ROUTES.EVENTS)
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Venues' }).click()
  await page.getByRole('link', { name: /Marina Hall/ }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Marina Hall' })).toBeVisible()

  await page.getByLabel('From').fill('2026-11-10')
  await page.getByLabel('To').fill('2026-11-11')
  await page.getByRole('button', { name: 'Show these days' }).click()
  await expect(page).toHaveURL(/from=2026-11-10&to=2026-11-11/)
  await expect(page.getByRole('region', { name: 'Tuesday 10 Nov' })).toBeVisible()
}

test('Venue Staff block a free morning, see it in the calendar, then remove it', async ({
  page,
}) => {
  await openMarinaHallOnTenAndElevenNovember(page, MOCK_ACCOUNTS.venueStaff)
  const tenth = page.getByRole('region', { name: 'Tuesday 10 Nov' })
  const eleventh = page.getByRole('region', { name: 'Wednesday 11 Nov' })
  await expect(tenth).toContainText('Stage lighting repair')
  await expect(eleventh).toContainText('Nothing booked or blocked.')

  const blocks = page.getByRole('region', { name: 'Blocks' })
  await blocks.getByLabel('Starts').fill('2026-11-11T10:00')
  await blocks.getByLabel('Ends').fill('2026-11-11T12:00')
  await blocks.getByLabel('Reason').fill('Fire alarm test')
  await blocks.getByRole('button', { name: 'Block venue' }).click()
  await expect(eleventh).toContainText('Blocked 10:00 am – 12:00 pm Fire alarm test')
  await expect(page.getByRole('list', { name: 'Blocks' })).toContainText('Fire alarm test')

  await page.getByRole('button', { name: 'Remove the block for Fire alarm test' }).click()
  await expect(eleventh).toContainText('Nothing booked or blocked.')
  await expect(page.getByRole('list', { name: 'Blocks' })).not.toContainText('Fire alarm test')
})

test('a block over confirmed bookings is saved and names the bookings it cuts into', async ({
  page,
}) => {
  await openMarinaHallOnTenAndElevenNovember(page, MOCK_ACCOUNTS.venueStaff)

  const blocks = page.getByRole('region', { name: 'Blocks' })
  await blocks.getByLabel('Starts').fill('2026-11-10T11:00')
  await blocks.getByLabel('Ends').fill('2026-11-10T14:00')
  await blocks.getByLabel('Reason').fill('Burst pipe')
  await blocks.getByRole('button', { name: 'Block venue' }).click()

  const report = page.getByRole('region', {
    name: 'Blocked. It cuts into these confirmed bookings, which are still booked:',
  })
  await expect(report).toContainText('Booking 512 for event 101, 10 Nov, 8:30 am – 12:30 pm')
  await expect(report).toContainText('Booking 511 for event 105, 10 Nov, 12:30 pm – 5:30 pm')
  await expect(page.getByRole('region', { name: 'Tuesday 10 Nov' })).toContainText('Burst pipe')
})

test('an Event Coordinator reads the calendar as bookings and maintenance, with no blocks to change', async ({
  page,
}) => {
  await openMarinaHallOnTenAndElevenNovember(page, MOCK_ACCOUNTS.coordinator)

  const tenth = page.getByRole('region', { name: 'Tuesday 10 Nov' })
  await expect(tenth).toContainText('Blocked 5:30 pm – 8:00 pm maintenance')
  await expect(tenth).toContainText('Booked 8:30 am – 12:30 pm booking')
  await expect(tenth).not.toContainText('Stage lighting repair')
  await expect(page.getByRole('region', { name: 'Blocks' })).toHaveCount(0)
})
