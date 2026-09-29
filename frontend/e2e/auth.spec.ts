import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

async function logIn(page: Page, account: { email: string; password: string }) {
  await page.getByLabel('Email').fill(account.email)
  await page.getByLabel('Password').fill(account.password)
  await page.getByRole('button', { name: 'Log in' }).click()
}

test('SCRUM-65: a new attendee signs up, lands on the events, and logs out', async ({ page }) => {
  await page.goto('/signup')

  await page.getByLabel('Full name').fill('Priya Nair')
  await page.getByLabel('Email').fill('priya@example.com')
  await page.getByLabel('Password').fill('Password123')
  await page.getByRole('button', { name: 'Create account' }).click()

  await expect(page).toHaveURL('/events')
  const header = page.getByRole('banner')
  await expect(header.getByText('Priya Nair')).toBeVisible()

  await header.getByRole('button', { name: 'Log out' }).click()
  await expect(page).toHaveURL('/')
  await expect(header.getByRole('link', { name: 'Log in' })).toBeVisible()
})

test('SCRUM-6: staff log in on their own page and reach the staff home', async ({ page }) => {
  const { coordinator } = MOCK_ACCOUNTS
  await page.goto('/staff/login')

  await logIn(page, coordinator)

  await expect(page).toHaveURL('/staff')
  await expect(page.getByText(`Welcome back, ${coordinator.full_name}.`)).toBeVisible()
})

test('SCRUM-6: a visitor sent to log in comes back to the page they asked for', async ({
  page,
}) => {
  const { organiser } = MOCK_ACCOUNTS
  await page.goto('/organiser')

  await expect(page).toHaveURL('/login?next=%2Forganiser')
  await logIn(page, organiser)

  await expect(page).toHaveURL('/organiser')
  await expect(page.getByText(`Welcome back, ${organiser.full_name}.`)).toBeVisible()
})

test('SCRUM-6: logging in from another page returns there, not to the role home', async ({
  page,
}) => {
  const { organiser } = MOCK_ACCOUNTS
  await page.goto(`/login?next=${encodeURIComponent('/events?page=2')}`)

  await logIn(page, organiser)

  await expect(page).toHaveURL('/events?page=2')
})
