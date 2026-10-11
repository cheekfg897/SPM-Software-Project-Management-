import { expect, test } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/** The smallest tap target a finger can hit reliably, in pixels. */
const MIN_TAP_TARGET = 44
/** The narrowest screen we support, where the header is tightest. */
const SMALL_PHONE = { width: 320, height: 640 }

test('SCRUM-28: an attendee opens their notifications and marks one read', async ({ page }) => {
  await page.setViewportSize(SMALL_PHONE)
  await signInAs(page, MOCK_ACCOUNTS.attendee)
  await page.goto('/events')

  // The counts come from the mock: two unread and one read (mocks/handlers/notifications.ts).
  const header = page.getByRole('banner')
  const bellWithTwo = header.getByRole('link', { name: 'Notifications, 2 unread' })
  await expect(bellWithTwo).toBeVisible()
  const bellBox = await bellWithTwo.boundingBox()
  expect(bellBox?.height).toBeGreaterThanOrEqual(MIN_TAP_TARGET)
  expect(bellBox?.width).toBeGreaterThanOrEqual(MIN_TAP_TARGET)

  const logOutBox = await header.getByRole('button', { name: 'Log out' }).boundingBox()
  expect(bellBox?.x).toBeDefined()
  expect((bellBox?.x ?? 0) + (bellBox?.width ?? 0)).toBeLessThanOrEqual(logOutBox?.x ?? 0)

  await bellWithTwo.click()
  await expect(page).toHaveURL('/notifications')
  const markReadButtons = page.getByRole('button', { name: 'Mark read' })
  await expect(markReadButtons).toHaveCount(2)

  await markReadButtons.first().click()

  await expect(header.getByRole('link', { name: 'Notifications, 1 unread' })).toBeVisible()
  await expect(markReadButtons).toHaveCount(1)
})
