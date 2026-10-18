import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { coordinatorEventPath, eventEquipmentPath } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'
import { MOCK_OPEN_EVENT_REFERENCE } from '../src/mocks/handlers/equipmentFixtures'

import { logIn } from './logIn'

/**
 * SCRUM-48: Technical Support open an event from their queue, are told a shortfall needs a note,
 * record that only part of the projectors can be provided, and the event's coordinator then sees
 * the outcome on its Equipment page (ADR-0077). Against the mock backend, which keeps its data
 * only until the page reloads, so the journey switches users through the app's own log-out and
 * log-in, never by reloading.
 */

const EVENT_NAME = 'Evening Product Showcase'
const NOTE = 'Two are out for repair; the venue has a screen you could use.'

/** The equipment lines table's row for the projectors, found by its Equipment cell. */
function projectorRow(page: Page) {
  return page
    .getByRole('table', { name: 'Equipment lines' })
    .getByRole('row')
    .filter({ has: page.getByRole('cell', { name: 'Projector', exact: true }) })
}

test('SCRUM-48: Technical Support record part of a request, and the coordinator sees it', async ({
  page,
}) => {
  await page.goto('/staff/login')
  await logIn(page, MOCK_ACCOUNTS.technicalSupport)
  await expect(page).toHaveURL('/staff')
  const queue = page.getByRole('list', { name: 'Equipment awaiting action' })
  await queue.getByRole('link', { name: new RegExp(EVENT_NAME) }).click()
  await expect(page).toHaveURL(eventEquipmentPath(MOCK_OPEN_EVENT_REFERENCE))

  await projectorRow(page).getByRole('button', { name: 'Record outcome for Projector' }).click()
  const form = page.getByRole('form', { name: 'Outcome for Projector' })
  await form.getByLabel('Quantity provided').fill('6')
  await form.getByRole('button', { name: 'Save outcome' }).click()
  await expect(
    form.getByText('A note is required unless the whole request can be provided.'),
  ).toBeVisible()

  await form.getByLabel('Note for the coordinator').fill(NOTE)
  await form.getByRole('button', { name: 'Save outcome' }).click()
  await expect(form).toBeHidden()
  await expect(projectorRow(page)).toContainText('Partially fulfilled')
  await expect(projectorRow(page)).toContainText('6 of 8 provided, short by 2')

  await page.getByRole('banner').getByRole('button', { name: 'Log out' }).click()
  await expect(page).toHaveURL('/')
  await page.getByRole('link', { name: 'Staff log in' }).click()
  await logIn(page, MOCK_ACCOUNTS.coordinator)
  await expect(page).toHaveURL('/staff')
  const assigned = page.getByRole('list', { name: 'Your assigned events' })
  await assigned.getByRole('link', { name: new RegExp(EVENT_NAME) }).click()
  await expect(page).toHaveURL(coordinatorEventPath(MOCK_OPEN_EVENT_REFERENCE))
  await page.getByRole('main').getByRole('link', { name: 'Equipment', exact: true }).click()

  await expect(page).toHaveURL(eventEquipmentPath(MOCK_OPEN_EVENT_REFERENCE))
  const projector = projectorRow(page)
  await expect(projector).toContainText('Partially fulfilled')
  await expect(projector).toContainText('6 of 8 provided, short by 2')
  await expect(projector).toContainText(NOTE)
  await expect(projector).toContainText('Reviewed by Tariq Hassan, 6 Oct, 9:15 am')
  await expect(page.getByRole('button', { name: /outcome/ })).toHaveCount(0)
})
