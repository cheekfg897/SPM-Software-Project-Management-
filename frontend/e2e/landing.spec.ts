import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const HEADLINE = 'Every event finds its orbit.'

/** Where the black hole's centre sits at the top of the page, as a share of the screen's
 *  height: CENTRE_HEIGHT_AT_TOP in src/features/landing/blackHole/geometry.ts. */
const CENTRE_HEIGHT_AT_TOP = 0.72

function hero(page: Page) {
  return page.getByRole('region', { name: HEADLINE })
}

async function scrollProgress(page: Page): Promise<number> {
  return Number(await hero(page).getAttribute('data-scroll-progress'))
}

/**
 * The brightness (0 to 255) of each canvas pixel straight up the middle, from the black
 * hole's centre to the top of the screen.
 */
async function brightnessAboveCentre(page: Page): Promise<number[]> {
  return page.evaluate((centreHeight) => {
    const canvas = document.querySelector('canvas')
    const context = canvas?.getContext('2d')
    if (!canvas || !context) {
      return []
    }
    const x = Math.round(canvas.width / 2)
    const centreY = Math.round(canvas.height * centreHeight)
    const column = context.getImageData(x, 0, 1, centreY).data
    const brightness: number[] = []
    for (let y = centreY - 1; y >= 0; y -= 1) {
      const offset = y * 4
      brightness.push((column[offset] + column[offset + 1] + column[offset + 2]) / 3)
    }
    return brightness
  }, CENTRE_HEIGHT_AT_TOP)
}

test.describe('SCRUM-5 landing page', () => {
  test('paints a black hole: a dark shadow with a bright ring over it', async ({ page }) => {
    await page.goto('/')
    await page.waitForTimeout(500)

    const brightness = await brightnessAboveCentre(page)

    // Just above the centre is the shadow; further up, the lensed arc and photon ring.
    expect(brightness[5]).toBeLessThan(40)
    expect(Math.max(...brightness)).toBeGreaterThan(180)
  })

  test('scrolling moves the scene and lifts the words away', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: HEADLINE })).toBeVisible()
    expect(await scrollProgress(page)).toBe(0)

    await page.mouse.wheel(0, 900)

    await expect.poll(() => scrollProgress(page)).toBeGreaterThan(0.4)
    await expect(page.getByRole('heading', { name: HEADLINE })).toBeHidden()
  })

  test('the hero links to the events and to sign-up', async ({ page }) => {
    await page.goto('/')

    await hero(page).getByRole('link', { name: 'Browse events' }).click()
    await expect(page).toHaveURL('/events')

    await page.goBack()
    await hero(page).getByRole('link', { name: 'Host an event' }).click()
    await expect(page).toHaveURL('/signup')
  })

  test('sections fade in as they scroll into view', async ({ page }) => {
    await page.goto('/')
    const attendees = page.getByRole('region', { name: 'Find something worth showing up for.' })
    const reveal = attendees.locator('[data-revealed]')
    await expect(reveal).toHaveAttribute('data-revealed', 'false')

    await attendees.scrollIntoViewIfNeeded()

    await expect(reveal).toHaveAttribute('data-revealed', 'true')
  })

  test('keeps still with reduced motion, and shows everything at once', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/')

    await page.mouse.wheel(0, 600)

    expect(await scrollProgress(page)).toBe(0)
    await expect(page.locator('[data-revealed="false"]')).toHaveCount(0)
  })

  test('never scrolls sideways', async ({ page }) => {
    await page.goto('/')

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    )

    expect(overflow).toBeLessThanOrEqual(0)
  })
})
