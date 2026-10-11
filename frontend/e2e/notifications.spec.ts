import { expect, test } from '@playwright/test'

import { MOCK_ACCOUNTS, mockSessionFor } from '../src/mocks/fixtures/accounts'

const SESSION_STORAGE_KEY = 'connectsphere.session'
const ATTENDEE_SESSION = mockSessionFor(MOCK_ACCOUNTS.attendee)
/** The smallest tap target a finger can hit reliably, in pixels. */
const MIN_TAP_TARGET = 44

test('SCRUM-28: an attendee opens their notifications and marks one read', async ({ page }) => {
  await page.addInitScript(([key, session]) => localStorage.setItem(key, session), [
    SESSION_STORAGE_KEY,
    JSON.stringify(ATTENDEE_SESSION),
  ] as const)
  await page.goto('/events')

  // The counts come from the mock: two unread and one read (mocks/handlers/notifications.ts).
  const header = page.getByRole('banner')
  const bellWithTwo = header.getByRole('link', { name: 'Notifications, 2 unread' })
  await expect(bellWithTwo).toBeVisible()
  const bellBox = await bellWithTwo.boundingBox()
  expect(bellBox?.height).toBeGreaterThanOrEqual(MIN_TAP_TARGET)
  expect(bellBox?.width).toBeGreaterThanOrEqual(MIN_TAP_TARGET)

  await bellWithTwo.click()
  await expect(page).toHaveURL('/notifications')
  const markReadButtons = page.getByRole('button', { name: 'Mark read' })
  await expect(markReadButtons).toHaveCount(2)

  await markReadButtons.first().click()

  await expect(header.getByRole('link', { name: 'Notifications, 1 unread' })).toBeVisible()
  await expect(markReadButtons).toHaveCount(1)
})
