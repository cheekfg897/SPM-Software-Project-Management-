import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { eventEquipmentPath, ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'
import { MOCK_OPEN_EVENT_REFERENCE } from '../src/mocks/handlers/equipmentFixtures'

import { signInAs } from './signInAs'

/**
 * SCRUM-47: Technical Support reserve every free projector for an event, take one out of service
 * as damaged from the projector's page, see the event's reservation flagged, then put the
 * projector back and see the flag go. Against the mock backend, which keeps its data only until
 * the page reloads, so the journey moves between the two pages with the browser's back and
 * forward buttons, never by reloading.
 */

const SHORT = 'Needs attention'

/** The event's reservation of projectors. */
function reservedProjectors(page: Page) {
  return page
    .getByRole('table', { name: 'Reserved equipment' })
    .getByRole('row')
    .filter({ hasText: 'Projector' })
}

/** How many projectors the event's availability says are free. */
function projectorAvailability(page: Page) {
  return page
    .getByRole('table', { name: 'Equipment availability' })
    .getByRole('row')
    .filter({ hasText: 'Projector' })
    .getByRole('cell')
    .nth(1)
}

function counts(page: Page) {
  return page.getByRole('group', { name: 'Units in and out of service' })
}

test('Technical Support take a damaged projector out of service and the reservation is flagged until it is back', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.technicalSupport)
  await page.goto(eventEquipmentPath(MOCK_OPEN_EVENT_REFERENCE))
  await page.getByLabel('Quantity of Projector').fill('6')
  await page.getByRole('button', { name: 'Reserve Projector' }).click()
  await expect(reservedProjectors(page)).toContainText('Not needed')
  await expect(projectorAvailability(page)).toHaveText('0')

  await page.getByRole('banner').getByRole('link', { name: 'Equipment' }).click()
  await expect(page).toHaveURL(ROUTES.EQUIPMENT_CATALOGUE)
  await page.getByRole('link', { name: 'Projector' }).click()
  await expect(counts(page)).toContainText('10 of 10')
  const form = page.getByRole('form', { name: 'Take units out of service' })
  await form.getByLabel('Quantity').fill('1')
  await form.getByLabel('Reason').selectOption('Damaged')
  await form.getByRole('button', { name: 'Take out of service' }).click()
  const outOfService = page.getByRole('table', { name: 'Units out of service' })
  await expect(outOfService).toContainText('Recorded by Tariq Hassan, 7 Oct, 2:05 pm')
  await expect(counts(page)).toContainText('9 of 10')

  await page.goBack()
  await page.goBack()
  await expect(page).toHaveURL(eventEquipmentPath(MOCK_OPEN_EVENT_REFERENCE))
  await expect(reservedProjectors(page)).toContainText(SHORT)
  await expect(page.getByText('Some reserved equipment is short')).toBeVisible()

  await page.goForward()
  await page.goForward()
  await page.getByRole('button', { name: 'Put 1 Damaged unit back in service' }).click()
  await expect(page.getByText('1 Damaged unit is back in service.')).toBeVisible()
  await expect(counts(page)).toContainText('10 of 10')

  await page.goBack()
  await page.goBack()
  await expect(reservedProjectors(page)).toContainText('Not needed')
  await expect(reservedProjectors(page)).not.toContainText(SHORT)
})
