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

for (const path of ['/', '/events', '/login', '/signup', '/staff/login']) {
  test(`${path} never scrolls sideways`, async ({ page }) => {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBe(0)
  })
}

/** A small phone: narrower than the mobile project's Pixel 7. */
const SMALL_PHONE = { width: 360, height: 740 }

test('every header control fits on a small phone', async ({ page }) => {
  await page.setViewportSize(SMALL_PHONE)
  await page.goto('/')
  const header = page.getByRole('banner')
  await expect(header.getByRole('link', { name: 'Sign up' })).toBeVisible()

  const controls = await header.locator('a, button').all()
  expect(controls.length).toBeGreaterThan(0)
  for (const control of controls) {
    const box = await control.boundingBox()
    expect(box, await control.innerText()).not.toBeNull()
    expect(box!.x + box!.width, await control.innerText()).toBeLessThanOrEqual(SMALL_PHONE.width)
  }
})
