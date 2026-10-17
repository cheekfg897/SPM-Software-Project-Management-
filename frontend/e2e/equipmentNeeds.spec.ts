import { expect, test } from '@playwright/test'

import { eventEquipmentPath } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'
import { MOCK_OPEN_EVENT_REFERENCE } from '../src/mocks/handlers/equipmentFixtures'

import { signInAs } from './signInAs'

/**
 * SCRUM-37: the event's coordinator records what equipment it needs, is told a quantity of zero
 * is refused, changes a line and removes it, on the event's Equipment page.
 */

test('the coordinator adds, changes and removes an equipment line', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.coordinator)
  await page.goto(eventEquipmentPath(MOCK_OPEN_EVENT_REFERENCE))

  const lines = page.getByRole('table', { name: 'Equipment lines' })
  await expect(lines.getByRole('row').filter({ hasText: 'Projector' })).toBeVisible()

  await page.getByLabel('Equipment type').selectOption({ label: 'Lectern' })
  await page.getByLabel('Quantity').fill('0')
  await page.getByRole('button', { name: 'Add line' }).click()
  await expect(page.getByText('Quantity must be at least 1.')).toBeVisible()

  await page.getByLabel('Quantity').fill('2')
  await page.getByLabel('Technical notes').fill('Stage left, by the screen')
  await page.getByRole('button', { name: 'Add line' }).click()
  // By its Equipment cell: the Projector line's notes mention "the lectern" too.
  const lectern = lines
    .getByRole('row')
    .filter({ has: page.getByRole('cell', { name: 'Lectern', exact: true }) })
  await expect(lectern).toContainText('Stage left, by the screen')
  await expect(lectern).toContainText('Awaiting Technical Support')

  await lines.getByRole('button', { name: 'Change Lectern' }).click()
  const changeForm = page.getByRole('form', { name: 'Change Lectern' })
  await expect(changeForm).toBeVisible()
  await changeForm.getByLabel('Quantity').fill('3')
  await changeForm.getByRole('button', { name: 'Save changes' }).click()
  await expect(changeForm).toBeHidden()
  await expect(lectern.getByRole('cell', { name: '3', exact: true })).toBeVisible()

  await lines.getByRole('button', { name: 'Remove Lectern' }).click()
  await expect(page.getByText('Remove Lectern from this event?')).toBeVisible()
  await page.getByRole('button', { name: 'Remove line' }).click()
  await expect(lectern).toHaveCount(0)
  await expect(lines.getByRole('row').filter({ hasText: 'Projector' })).toBeVisible()
})
