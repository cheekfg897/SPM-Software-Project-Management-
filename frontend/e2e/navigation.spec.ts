import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'

import { ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'
import type { MockAccount } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

import { expectHeaderControlsWithin } from './headerFits'

/** Every page a visitor can open without signing in. */
const PUBLIC_PATHS = ['/', '/events', '/login', '/signup', '/staff/login']

/** A small phone: narrower than the mobile project's Pixel 7. */
const SMALL_PHONE = { width: 360, height: 740 }

/** A tablet held upright: still too narrow for staff's links in the bar (below lg). */
const TABLET = { width: 768, height: 1024 }

/** Wide enough for every link in one bar (lg and up). */
const LAPTOP = { width: 1280, height: 800 }

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

/** The header of the page `account` lands on when signed in, at `viewport`. */
async function headerFor(page: Page, account: MockAccount, viewport: typeof SMALL_PHONE) {
  await page.setViewportSize(viewport)
  await signInAs(page, account)
  await page.goto(ROUTES.EVENTS)
  const header = page.getByRole('banner')
  await expect(header.getByRole('button', { name: 'Log out' })).toBeVisible()
  return header
}

async function boxOf(locator: Locator) {
  const box = await locator.boundingBox()
  if (box === null) {
    throw new Error('Expected the control to be on screen.')
  }
  return box
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
  await expect(page.getByRole('banner').getByRole('link', { name: 'Sign up' })).toBeVisible()

  await expectHeaderControlsWithin(page, SMALL_PHONE.width)
})

const NARROW_SCREENS = [
  ['phone', SMALL_PHONE],
  ['tablet', TABLET],
] as const

for (const [screen, viewport] of NARROW_SCREENS) {
  test(`on a ${screen} staff's links take a row under the bar, which keeps the logo and Log out`, async ({
    page,
  }) => {
    const header = await headerFor(page, MOCK_ACCOUNTS.coordinator, viewport)

    const logo = await boxOf(header.getByRole('link', { name: 'ConnectSphere' }))
    const logOut = await boxOf(header.getByRole('button', { name: 'Log out' }))
    const clients = await boxOf(header.getByRole('link', { name: 'Clients' }))
    expect(logOut.y).toBeLessThan(logo.y + logo.height)
    // At the bar's right end, past its 16px padding and a little more.
    expect(logOut.x + logOut.width).toBeGreaterThan(viewport.width - 32)
    expect(clients.y).toBeGreaterThanOrEqual(logOut.y + logOut.height)
  })
}

test("on a wide screen staff's links sit in the bar, after the logo", async ({ page }) => {
  const header = await headerFor(page, MOCK_ACCOUNTS.coordinator, LAPTOP)

  const logo = await boxOf(header.getByRole('link', { name: 'ConnectSphere' }))
  const clients = await boxOf(header.getByRole('link', { name: 'Clients' }))
  expect(clients.x).toBeGreaterThan(logo.x + logo.width)
  expect(clients.y).toBeLessThan(logo.y + logo.height)
})

test("on a phone an attendee's links stay in the bar, beside the logo", async ({ page }) => {
  const header = await headerFor(page, MOCK_ACCOUNTS.attendee, SMALL_PHONE)

  const logo = await boxOf(header.getByRole('link', { name: 'ConnectSphere' }))
  const myEvents = await boxOf(header.getByRole('link', { name: 'My events' }))
  expect(myEvents.x).toBeGreaterThan(logo.x + logo.width)
  expect(myEvents.y).toBeLessThan(logo.y + logo.height)
})
