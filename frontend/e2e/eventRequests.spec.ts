import { expect, test } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { logIn } from './logIn'
import { signInAs } from './signInAs'

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

test('SCRUM-19: an organiser submits a new event request and sees it in their list', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.organiser)
  await page.goto('/organiser')

  await page.getByRole('link', { name: 'New event request' }).click()
  await expect(page).toHaveURL('/organiser/requests/new')
  await page.getByLabel('Event name').fill('Harbour Lights Gala')
  await page.getByLabel('Date', { exact: true }).fill('2026-11-20')
  await page.getByLabel('Starts').fill('19:00')
  await page.getByLabel('Ends', { exact: true }).fill('23:00')
  await page.getByLabel('Expected attendance').fill('300')
  await page.getByLabel('Accessibility needs').fill('Step-free access')
  await page
    .getByRole('radiogroup', { name: 'Do attendees need to register?' })
    .getByText('Yes')
    .click()
  await page.getByRole('button', { name: 'Submit request' }).click()

  await expect(page).toHaveURL('/organiser')
  const newest = page
    .getByRole('list', { name: 'Your event requests' })
    .getByRole('listitem')
    .first()
  await expect(newest.getByRole('heading', { name: 'Harbour Lights Gala' })).toBeVisible()
  await expect(newest.getByText('Submitted')).toBeVisible()
})

test('SCRUM-20: an organiser saves a draft, comes back to it and submits it', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.organiser)
  await page.goto('/organiser/requests/new')

  await page.getByLabel('Event name').fill('Spring Fair')
  await page.getByRole('button', { name: 'Save as draft' }).click()
  await expect(page).toHaveURL('/organiser')
  const list = page.getByRole('list', { name: 'Your event requests' })
  const draft = list.getByRole('listitem').first()
  await expect(draft.getByText('Draft')).toBeVisible()

  await draft.getByRole('link').click()
  await expect(page.getByRole('heading', { name: 'Edit draft', level: 1 })).toBeVisible()
  await expect(page.getByLabel('Event name')).toHaveValue('Spring Fair')
  await page.getByLabel('Date', { exact: true }).fill('2026-11-21')
  await page.getByLabel('Starts').fill('10:00')
  await page.getByLabel('Ends', { exact: true }).fill('16:00')
  await page.getByLabel('Expected attendance').fill('80')
  await page.getByRole('button', { name: 'Submit request' }).click()

  await expect(page).toHaveURL('/organiser')
  const submitted = list.getByRole('listitem').filter({ hasText: 'Spring Fair' })
  await expect(submitted.getByText('Submitted')).toBeVisible()
})
