import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'
import type { MockAccount } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/** SCRUM-25 and SCRUM-67: Venue Staff keep the venue catalogue from the web app. */

/**
 * Open the venue list from the header and wait for its rows. It moves within the app, never
 * reloading the page, since the mock backend forgets its changes on a reload.
 */
async function openVenuesFromHeader(page: Page) {
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Venues' }).click()
  await expect(page).toHaveURL(ROUTES.VENUES)
  await expect(page.getByRole('link', { name: /Marina Hall/ })).toBeVisible()
}

/** Start signed in as `account`, on the venue list. */
async function startOnVenues(page: Page, account: MockAccount) {
  await signInAs(page, account)
  await page.goto(ROUTES.EVENTS)
  await openVenuesFromHeader(page)
}

test('Venue Staff add a venue, are refused a blank name, then fix it and change it', async ({
  page,
}) => {
  await startOnVenues(page, MOCK_ACCOUNTS.venueStaff)

  await page.getByRole('link', { name: 'Add a venue' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Add a venue' })).toBeVisible()
  await page.getByLabel('Location').fill('Level 9, Tower Block')
  await page.getByLabel('Capacity').fill('64')
  await page.getByLabel('Facilities').fill('Projector\nStage')
  await page.getByRole('button', { name: 'Add venue' }).click()
  await expect(page.getByText('Must not be blank.')).toBeVisible()
  await expect(page.getByLabel('Name')).toBeFocused()

  await page.getByLabel('Name').fill('Skyline Room')
  await page.getByRole('button', { name: 'Add venue' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Skyline Room' })).toBeVisible()
  await expect(page.getByText('projector, stage')).toBeVisible()

  await page.getByRole('link', { name: 'Edit venue' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Edit Skyline Room' })).toBeVisible()
  await page.getByLabel('Capacity').fill('80')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Skyline Room' })).toBeVisible()
  await expect(page.getByText('Up to 80 people')).toBeVisible()
})

test('a longer turnaround saves, and shows the bookings it now overlaps (SCRUM-67)', async ({
  page,
}) => {
  await startOnVenues(page, MOCK_ACCOUNTS.venueStaff)

  await page.getByRole('link', { name: /Marina Hall/ }).click()
  await page.getByRole('link', { name: 'Edit venue' }).click()
  await expect(page.getByLabel('Turnaround time (minutes)')).toHaveValue('30')
  await page.getByLabel('Turnaround time (minutes)').fill('45')
  await page.getByRole('button', { name: 'Save changes' }).click()

  const report = page.getByRole('region', { name: 'Saved, but some bookings now overlap' })
  await expect(report).toContainText('Bookings 512 and 511 overlap on 10 Nov')
  await expect(report).toContainText('Booking 511 runs into block 71 on 10 Nov')
  await report.getByRole('link', { name: 'Back to the venue' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Marina Hall' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Setup and turnaround' })).toContainText(
    '45 minutes',
  )
})

test('Venue Staff deactivate a venue, which leaves the list, then reactivate it', async ({
  page,
}) => {
  await startOnVenues(page, MOCK_ACCOUNTS.venueStaff)

  await page.getByRole('link', { name: /Garden Pavilion/ }).click()
  await page.getByRole('button', { name: 'Deactivate venue' }).click()
  await expect(page.getByText(/This venue is deactivated/)).toBeVisible()

  await openVenuesFromHeader(page)
  await expect(page.getByRole('link', { name: /Garden Pavilion/ })).toHaveCount(0)

  await page.goBack()
  await page.getByRole('button', { name: 'Reactivate venue' }).click()
  await expect(page.getByText(/This venue is deactivated/)).toHaveCount(0)
  await openVenuesFromHeader(page)
  await expect(page.getByRole('link', { name: /Garden Pavilion/ })).toBeVisible()
})

test('an Event Coordinator reads a venue but is offered no changes', async ({ page }) => {
  await startOnVenues(page, MOCK_ACCOUNTS.coordinator)

  await page.getByRole('link', { name: /Boardroom Two/ }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Boardroom Two' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Opening hours' })).toContainText('Monday')
  await expect(page.getByRole('link', { name: 'Edit venue' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Add a venue' })).toHaveCount(0)
})

test('the staff header, Venues link included, fits on a small phone', async ({ page }) => {
  const smallPhone = { width: 360, height: 740 }
  await page.setViewportSize(smallPhone)
  await startOnVenues(page, MOCK_ACCOUNTS.venueStaff)

  const controls = await page.getByRole('banner').locator('a, button').all()
  expect(controls.length).toBeGreaterThan(0)
  for (const control of controls) {
    const box = await control.boundingBox()
    expect(box, await control.innerText()).not.toBeNull()
    expect(box!.x + box!.width, await control.innerText()).toBeLessThanOrEqual(smallPhone.width)
  }
})
