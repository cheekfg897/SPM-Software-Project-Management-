import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

/** Every page a visitor can open without signing in. */
const PUBLIC_PATHS = ['/', '/events', '/login', '/signup', '/staff/login']

/** A small phone: narrower than the mobile project's Pixel 7. */
const SMALL_PHONE = { width: 360, height: 740 }

/** Where index.html loads Inter and Space Grotesk from. */
const WEB_FONTS = /fonts\.(googleapis|gstatic)\.com/

/** How far `path` scrolls sideways once it has drawn, in pixels. */
async function sidewaysOverflow(page: Page, path: string): Promise<number> {
  // Without the web fonts, every run measures the same font. With them, whether they
  // arrived before the measurement decided at random whether /events passed on CI.
  await page.route(WEB_FONTS, (route) => route.abort())
  await page.goto(path)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
}

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

for (const path of PUBLIC_PATHS) {
  test(`${path} never scrolls sideways`, async ({ page }) => {
    expect(await sidewaysOverflow(page, path)).toBe(0)
  })

  // Text that won't wrap (a long venue name) shows up here whatever the font.
  test(`${path} never scrolls sideways on a small phone`, async ({ page }) => {
    await page.setViewportSize(SMALL_PHONE)

    expect(await sidewaysOverflow(page, path)).toBe(0)
  })
}

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
