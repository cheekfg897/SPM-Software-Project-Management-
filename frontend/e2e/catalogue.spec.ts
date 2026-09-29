import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

/**
 * SCRUM-52: the event catalogue, against the mock catalogue (docs/adr/0032). The mock's
 * "now" is Monday 5 October 2026, so the same events show on every run.
 */

const SESSION_STORAGE_KEY = 'connectsphere.session'
const ATTENDEE_SESSION = {
  accessToken: 'mock-attendee-token',
  user: { id: 101, full_name: 'Alice Tan', role: 'attendee' },
}

function card(page: Page, eventName: string) {
  return page.getByRole('article').filter({ has: page.getByRole('heading', { name: eventName }) })
}

/** Click a filter choice by its visible text, as a user would. */
async function chooseWhen(page: Page, label: string) {
  await page.getByRole('radiogroup', { name: 'When' }).getByText(label, { exact: true }).click()
}

test('a visitor browses, searches, filters and pages through the catalogue', async ({ page }) => {
  await page.goto('/events')
  await expect(page.getByText('29 events')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Pagination' })).toContainText('Page 1 of 3')

  await page.getByRole('searchbox', { name: 'Search events' }).fill('jazz')
  await expect(page).toHaveURL('/events?q=jazz')
  await expect(page.getByText('1 event', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Jazz by the Bay' })).toBeVisible()

  await page.getByRole('searchbox', { name: 'Search events' }).fill('')
  await chooseWhen(page, 'This weekend')
  await expect(page).toHaveURL('/events?when=this_weekend')
  await expect(page.getByRole('heading', { name: 'Family Science Saturday' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Data Viz Meetup' })).toHaveCount(0)

  await chooseWhen(page, 'Pick dates')
  await page.getByLabel('From', { exact: true }).fill('2026-10-20T00:00')
  await page.getByLabel('To', { exact: true }).fill('2026-10-25T23:59')
  await expect(page.getByRole('heading', { name: 'Poetry at the Gallery' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Family Science Saturday' })).toHaveCount(0)

  await chooseWhen(page, 'Upcoming')
  await page.getByRole('button', { name: 'Next page' }).click()
  await expect(page).toHaveURL('/events?page=2')
  await expect(page.getByRole('navigation', { name: 'Pagination' })).toContainText('Page 2 of 3')
})

test('the backend refuses a range that ends before it starts, and says why', async ({ page }) => {
  await page.goto('/events?starts_from=2026-10-25T00%3A00&starts_to=2026-10-20T00%3A00')

  await expect(page.getByText('Must be after starts_from.')).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('Invalid request.')
})

test('a visitor who clicks Register is asked to log in first', async ({ page }) => {
  await page.goto('/events?q=jazz')

  await card(page, 'Jazz by the Bay').getByRole('button', { name: 'Register' }).click()

  await expect(page).toHaveURL(`/login?next=${encodeURIComponent('/events?q=jazz')}`)
})

test('an attendee registers for an event', async ({ page }) => {
  await page.addInitScript(([key, session]) => localStorage.setItem(key, session), [
    SESSION_STORAGE_KEY,
    JSON.stringify(ATTENDEE_SESSION),
  ] as const)
  await page.goto('/events')
  const jazz = card(page, 'Jazz by the Bay')
  await expect(jazz.getByText('12 places left')).toBeVisible()

  await jazz.getByRole('button', { name: 'Register' }).click()

  await expect(jazz.getByText("You're registered")).toBeVisible()
  await expect(jazz.getByRole('button', { name: 'Register' })).toHaveCount(0)
})
