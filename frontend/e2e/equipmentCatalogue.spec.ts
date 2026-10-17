import { expect, test } from '@playwright/test'

import { ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/** SCRUM-27: Technical Support keep the equipment catalogue; other staff read it. */

/** A small phone: narrower than the mobile project's Pixel 7. */
const SMALL_PHONE = { width: 360, height: 740 }

test('Technical Support add a type, then correct how many are held', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.technicalSupport)
  await page.goto(ROUTES.HOME)

  await page.getByRole('banner').getByRole('link', { name: 'Equipment' }).click()
  const catalogue = page.getByRole('table', { name: 'Equipment types' })
  await expect(catalogue.getByRole('link', { name: 'Projector' })).toBeVisible()

  await page.getByRole('link', { name: 'Add equipment type' }).click()
  await page.getByLabel('Name', { exact: true }).fill('Folding table')
  await page.getByLabel('Total quantity held').fill('2')
  await page.getByLabel('Store name').fill('Jurong store')
  await page.getByRole('button', { name: 'Add equipment type' }).click()

  await expect(page.getByRole('heading', { level: 1, name: 'Folding table' })).toBeVisible()
  await expect(page.getByText('Store: Jurong store')).toBeVisible()

  await page.getByRole('link', { name: 'Edit' }).click()
  await expect(page.getByLabel('Total quantity held')).toHaveValue('2')
  await page.getByLabel('Total quantity held').fill('3')
  await page.getByRole('button', { name: 'Save changes' }).click()

  await expect(page.getByRole('heading', { level: 1, name: 'Folding table' })).toBeVisible()
  await expect(page.getByRole('definition').filter({ hasText: /^3$/ })).toBeVisible()

  await page.getByRole('link', { name: 'All equipment' }).click()
  const foldingTable = catalogue.getByRole('row').filter({ hasText: 'Folding table' })
  await expect(foldingTable).toContainText('Store: Jurong store')
  await expect(foldingTable.getByRole('cell').nth(2)).toHaveText('3')
})

test('an Event Coordinator reads a type but is offered no way to change it', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.coordinator)
  await page.goto(ROUTES.EQUIPMENT_CATALOGUE)

  await page.getByRole('link', { name: 'Microphone' }).click()

  await expect(page.getByRole('heading', { level: 1, name: 'Microphone' })).toBeVisible()
  await expect(page.getByText('Venue 3')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Edit' })).toHaveCount(0)
})

test("every header control fits on a small phone with a staff member's links", async ({ page }) => {
  await page.setViewportSize(SMALL_PHONE)
  await signInAs(page, MOCK_ACCOUNTS.technicalSupport)
  await page.goto(ROUTES.HOME)
  const header = page.getByRole('banner')
  await expect(header.getByRole('link', { name: 'Equipment' })).toBeVisible()

  const controls = await header.locator('a, button').all()
  for (const control of controls) {
    const box = await control.boundingBox()
    expect(box, await control.innerText()).not.toBeNull()
    expect(box!.x + box!.width, await control.innerText()).toBeLessThanOrEqual(SMALL_PHONE.width)
  }
})
