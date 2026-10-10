import { expect, test } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { logIn } from './logIn'

test("SCRUM-7: an organiser logs in and sees their organisation's event requests", async ({
  page,
}) => {
  await page.goto('/login')

  await logIn(page, MOCK_ACCOUNTS.organiser)

  await expect(page).toHaveURL('/organiser')
  await expect(page.getByRole('heading', { name: 'Your events', level: 1 })).toBeVisible()
  const list = page.getByRole('list', { name: 'Your event requests' })
  // In mock mode the app mounts once the mock worker starts: wait for a row before reading them.
  await expect(list.getByRole('heading', { name: 'Partner Summit' })).toBeVisible()

  await expect(list.getByRole('listitem')).toHaveCount(6)
  const summit = list.getByRole('listitem').filter({ hasText: 'Partner Summit' })
  await expect(summit.getByText('Under review')).toBeVisible()
  await expect(summit.getByText('Thu, 12 Nov · 9:00 am – 5:00 pm')).toBeVisible()
  const draft = list.getByRole('listitem').filter({ hasText: 'Volunteer Thank-You Dinner' })
  await expect(draft.getByText('Draft')).toBeVisible()
  await expect(draft.getByText('Date to be set')).toBeVisible()
})
