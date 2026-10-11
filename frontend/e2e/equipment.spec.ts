import { expect, test } from '@playwright/test'

import { eventEquipmentPath } from '../src/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '../src/mocks/fixtures/accounts'
import { MOCK_OPEN_EVENT_REFERENCE } from '../src/mocks/handlers/equipmentFixtures'

/** SCRUM-45/46: a Technical Support member checks and reserves equipment for an event. */

const SESSION_STORAGE_KEY = 'connectsphere.session'
const TECHNICAL_SUPPORT_SESSION = mockSessionFor(MOCK_ACCOUNTS.technicalSupport)

test('Technical Support sees the shortfall, over-reserves, then reserves what is free', async ({
  page,
}) => {
  await page.addInitScript(([key, session]) => localStorage.setItem(key, session), [
    SESSION_STORAGE_KEY,
    JSON.stringify(TECHNICAL_SUPPORT_SESSION),
  ] as const)
  await page.goto(eventEquipmentPath(MOCK_OPEN_EVENT_REFERENCE))

  const availability = page.getByRole('table', { name: 'Equipment availability' })
  const projector = availability.getByRole('row').filter({ hasText: 'Projector' })
  await expect(projector).toContainText('Short by 2')

  await page.getByLabel('Quantity of Projector').fill('7')
  await page.getByRole('button', { name: 'Reserve Projector' }).click()
  await expect(page.getByText('Only 6 available for this period.')).toBeVisible()

  await page.getByLabel('Quantity of Projector').fill('4')
  await page.getByRole('button', { name: 'Reserve Projector' }).click()
  await expect(projector).toContainText('Short by 6')
  await expect(
    page.getByRole('table', { name: 'Reserved equipment' }).getByText('Tariq Hassan'),
  ).toBeVisible()
})
