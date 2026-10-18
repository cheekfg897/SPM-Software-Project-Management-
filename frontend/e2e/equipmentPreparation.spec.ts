import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { coordinatorEventPath, eventEquipmentPath, ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'
import { MOCK_OPEN_EVENT_REFERENCE } from '../src/mocks/handlers/equipmentFixtures'

import { logIn } from './logIn'
import { signInAs } from './signInAs'

/**
 * SCRUM-85: Technical Support reserve a projector, record it as ready with a note, and the
 * event's coordinator then sees both on its Equipment page (ADR-0081). Against the mock backend,
 * which keeps its data only until the page reloads, so the journey switches users through the
 * app's own log-out and log-in.
 */

const EVENT_NAME = 'Evening Product Showcase'
const NOTE = 'Lamps tested, spare cable packed.'

/** The reserved equipment table's row for the projectors. */
function projectorRow(page: Page) {
  return page
    .getByRole('table', { name: 'Reserved equipment' })
    .getByRole('row')
    .filter({ has: page.getByRole('cell', { name: 'Projector', exact: true }) })
}

test('SCRUM-85: Technical Support record a reservation as ready, and the coordinator sees it', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.technicalSupport)
  await page.goto(eventEquipmentPath(MOCK_OPEN_EVENT_REFERENCE))
  await page.getByLabel('Quantity of Projector').fill('2')
  await page.getByRole('button', { name: 'Reserve Projector' }).click()
  await expect(projectorRow(page)).toContainText('Not started')

  await projectorRow(page).getByLabel('Preparation status for Projector').selectOption('ready')
  await projectorRow(page).getByLabel('Preparation notes for Projector').fill(NOTE)
  await projectorRow(page).getByRole('button', { name: 'Save preparation for Projector' }).click()
  await expect(projectorRow(page).getByRole('cell', { name: 'Ready', exact: true })).toBeVisible()

  await page.getByRole('banner').getByRole('button', { name: 'Log out' }).click()
  await expect(page).toHaveURL(ROUTES.HOME)
  await page.getByRole('link', { name: 'Staff log in' }).click()
  await logIn(page, MOCK_ACCOUNTS.coordinator)
  await expect(page).toHaveURL(ROUTES.STAFF_HOME)
  const assigned = page.getByRole('list', { name: 'Your assigned events' })
  await assigned.getByRole('link', { name: new RegExp(EVENT_NAME) }).click()
  await expect(page).toHaveURL(coordinatorEventPath(MOCK_OPEN_EVENT_REFERENCE))
  await page.getByRole('main').getByRole('link', { name: 'Equipment', exact: true }).click()

  await expect(page).toHaveURL(eventEquipmentPath(MOCK_OPEN_EVENT_REFERENCE))
  await expect(projectorRow(page).getByRole('cell', { name: 'Ready', exact: true })).toBeVisible()
  await expect(projectorRow(page)).toContainText(NOTE)
  await expect(page.getByRole('button', { name: /Save preparation/ })).toHaveCount(0)
})
