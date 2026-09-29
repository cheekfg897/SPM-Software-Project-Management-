import { expect, test } from '@playwright/test'

test('a visitor can reach every public page from the header and footer', async ({ page }) => {
  await page.goto('/')

  await page.getByRole('banner').getByRole('link', { name: 'Log in' }).click()
  await expect(page).toHaveURL('/login')

  await page.getByRole('banner').getByRole('link', { name: 'Sign up' }).click()
  await expect(page).toHaveURL('/signup')

  await page.getByRole('link', { name: 'Staff log in' }).click()
  await expect(page).toHaveURL('/staff/login')
})

test('an unknown address shows the not found page', async ({ page }) => {
  await page.goto('/nowhere')

  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
})
