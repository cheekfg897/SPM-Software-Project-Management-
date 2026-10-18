import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'

/** Check that every link and button in the header ends inside a screen `width` pixels wide. */
export async function expectHeaderControlsWithin(page: Page, width: number) {
  const controls = await page.getByRole('banner').locator('a, button').all()
  expect(controls.length).toBeGreaterThan(0)
  for (const control of controls) {
    const box = await control.boundingBox()
    expect(box, await control.innerText()).not.toBeNull()
    expect(box!.x + box!.width, await control.innerText()).toBeLessThanOrEqual(width)
  }
}
