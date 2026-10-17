import { expect, test } from '@playwright/test'

import { ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'
import { MOCK_ORGANISATIONS } from '../src/mocks/handlers/organisationFixtures'

import { signInAs } from './signInAs'

/** SCRUM-66: staff find the client organisations from the header and record a new one. */

const SMALL_PHONE = { width: 320, height: 640 }

test('Venue Staff open the organisations from the header and record one', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.venueStaff)
  await page.goto(ROUTES.EVENTS)

  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'Clients' })
    .click()
  await expect(page).toHaveURL(ROUTES.ORGANISATIONS)
  const table = page.getByRole('table', { name: 'Client organisations' })
  await expect(table.getByRole('row')).toHaveCount(MOCK_ORGANISATIONS.length + 1)

  await page.getByLabel('Organisation name').fill('Bayfront Partners')
  await page.getByLabel('Contact name').fill('Wei Ling Tan')
  await page.getByLabel('Contact email').fill('weiling@bayfront.test')
  await page.getByRole('button', { name: 'Record organisation' }).click()

  await expect(page.getByRole('status')).toContainText('Its organisation ID is 4')
  await expect(table.getByRole('row').filter({ hasText: 'Bayfront Partners' })).toContainText(
    'weiling@bayfront.test',
  )
})

test('every header control fits on a small phone for staff', async ({ page }) => {
  await page.setViewportSize(SMALL_PHONE)
  await signInAs(page, MOCK_ACCOUNTS.coordinator)
  await page.goto(ROUTES.ORGANISATIONS)
  const header = page.getByRole('banner')
  await expect(header.getByRole('link', { name: 'Clients' })).toBeVisible()

  const controls = await header.locator('a, button').all()
  for (const control of controls) {
    const box = await control.boundingBox()
    expect(box, await control.innerText()).not.toBeNull()
    expect(box!.x + box!.width, await control.innerText()).toBeLessThanOrEqual(SMALL_PHONE.width)
  }
})
