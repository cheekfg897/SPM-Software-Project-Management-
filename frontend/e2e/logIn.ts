import type { Page } from '@playwright/test'

/** Fill in either log-in page (external or staff) with the account's details and submit it. */
export async function logIn(page: Page, account: { email: string; password: string }) {
  await page.getByLabel('Email').fill(account.email)
  await page.getByLabel('Password').fill(account.password)
  await page.getByRole('button', { name: 'Log in' }).click()
}
