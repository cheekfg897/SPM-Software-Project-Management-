import { expect, test } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

test('SCRUM-28: an attendee opens their notifications and marks one read', async ({ page }) => {
  const { attendee } = MOCK_ACCOUNTS
  await page.goto('/login')
  await page.getByLabel('Email').fill(attendee.email)
  await page.getByLabel('Password').fill(attendee.password)
  await page.getByRole('button', { name: 'Log in' }).click()

  const header = page.getByRole('banner')
  await expect(header.getByRole('link', { name: 'Notifications, 2 unread' })).toBeVisible()

  await header.getByRole('link', { name: 'Notifications, 2 unread' }).click()
  await expect(page).toHaveURL('/notifications')
  const markReadButtons = page.getByRole('button', { name: 'Mark read' })
  await expect(markReadButtons).toHaveCount(2)

  await markReadButtons.first().click()

  await expect(header.getByRole('link', { name: 'Notifications, 1 unread' })).toBeVisible()
  await expect(markReadButtons).toHaveCount(1)
})
