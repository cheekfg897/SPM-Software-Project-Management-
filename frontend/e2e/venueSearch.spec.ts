import { expect, test } from '@playwright/test'

import { coordinatorEventPath, ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { expectHeaderControlsWithin } from './headerFits'
import { signInAs } from './signInAs'

/** SCRUM-35/36: a coordinator searches for venues, then checks one the search left out. */

/** The narrowest screen we support, where the header is tightest. */
const SMALL_PHONE = { width: 320, height: 640 }

test('a coordinator finds the free venues for an event and learns why another does not suit', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.coordinator)
  await page.goto(ROUTES.STAFF_HOME)

  await page.getByRole('banner').getByRole('link', { name: 'Find a venue' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Find a venue' })).toBeVisible()

  await page.getByLabel('Date', { exact: true }).fill('2026-11-20')
  await page.getByLabel('Start time').fill('09:00')
  await page.getByLabel('End time').fill('17:00')
  await page.getByLabel('Minimum capacity').fill('120')
  await page.getByLabel('Accessibility requirements').fill('step-free access')
  await page.getByRole('button', { name: 'Search venues' }).click()
  await expect(page).toHaveURL(/min_capacity=120/)

  const results = page.getByRole('list', { name: 'Venues that match' })
  await expect(results.getByRole('heading', { level: 3 })).toHaveText([
    'Garden Pavilion',
    'Harbourfront Hall',
    'Marina Hall',
  ])
  await expect(page.getByRole('article', { name: 'Garden Pavilion' })).toContainText(
    'step-free access',
  )

  await page.getByLabel('Venue', { exact: true }).selectOption('Orchid Room')
  await page.getByRole('button', { name: 'Check venue' }).click()
  await expect(page.getByText('Not suitable for this event')).toBeVisible()
  const reasons = page.getByRole('list', { name: 'Why it is not suitable' })
  await expect(reasons.getByRole('listitem')).toHaveText([
    "Expected attendance of 120 exceeds the venue's capacity of 100.",
    'The venue does not offer step-free access.',
  ])

  await page.getByLabel('Venue', { exact: true }).selectOption('Harbourfront Hall')
  await page.getByRole('button', { name: 'Check venue' }).click()
  await expect(page.getByText('Suitable for this event', { exact: true })).toBeVisible()
})

test("SCRUM-90: a coordinator opens venue search from an event, sets what it couldn't fill, and searches", async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.coordinator)
  await page.goto(coordinatorEventPath('EVR-7K2M9QXA'))

  await page.getByRole('link', { name: 'Find a venue for this event' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Find a venue' })).toBeVisible()
  const note = page.getByRole('region', { name: 'What Partner Summit asked for' })
  await expect(note).toContainText('A main hall for 250 and four breakout rooms.')
  await expect(page.getByLabel('Date', { exact: true })).toHaveValue('2026-11-12')
  await expect(page.getByLabel('Minimum capacity')).toHaveValue('250')

  await page.getByLabel('Room layout').selectOption('Theatre')
  await page.getByRole('button', { name: 'Search venues' }).click()

  await expect(page).toHaveURL(/required_layout=theatre/)
  await expect(page.getByRole('article', { name: 'Harbourfront Hall' })).toBeVisible()
  await expect(note).toBeVisible()
})

test("every header control fits a coordinator's small phone", async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.coordinator)
  await page.setViewportSize(SMALL_PHONE)
  await page.goto(ROUTES.VENUE_SEARCH)
  await expect(page.getByRole('banner').getByRole('link', { name: 'Find a venue' })).toBeVisible()

  await expectHeaderControlsWithin(page, SMALL_PHONE.width)
})
