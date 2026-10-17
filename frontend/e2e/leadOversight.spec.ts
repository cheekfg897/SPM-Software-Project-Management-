import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

const AISHA = MOCK_ACCOUNTS.otherCoordinator

/** Open the oversight page from the Lead's navigation and wait until it has loaded. */
async function openOversight(page: Page) {
  await page
    .getByRole('navigation', { name: 'Lead' })
    .getByRole('link', { name: 'Oversight' })
    .click()
  await expect(page).toHaveURL('/staff/oversight')
  await expect(page.getByRole('heading', { name: 'Coordinator oversight', level: 1 })).toBeVisible()
}

function workloadOf(page: Page, coordinator: string) {
  return page.getByRole('region', { name: 'Workload' }).getByRole('article', { name: coordinator })
}

function activeEvent(page: Page, name: string) {
  return page.getByRole('region', { name: 'Active events' }).getByRole('article', { name })
}

test('SCRUM-96: the Lead moves an event to another coordinator and sees the workload follow', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.lead)
  await page.goto('/staff/queue')
  await openOversight(page)

  const gala = activeEvent(page, 'Harbourfront Gala Dinner')
  await expect(gala.getByText(MOCK_ACCOUNTS.coordinator.full_name)).toBeVisible()
  await expect(workloadOf(page, AISHA.full_name).getByText('Harbourfront Gala Dinner')).toHaveCount(
    0,
  )
  await gala.getByLabel('Coordinator email for Harbourfront Gala Dinner').fill(AISHA.email)
  await gala.getByRole('button', { name: 'Reassign Harbourfront Gala Dinner' }).click()

  await expect(gala.getByText(AISHA.full_name)).toBeVisible()
  await expect(
    workloadOf(page, AISHA.full_name).getByText('Harbourfront Gala Dinner'),
  ).toBeVisible()
  await expect(
    workloadOf(page, MOCK_ACCOUNTS.coordinator.full_name).getByText('Harbourfront Gala Dinner'),
  ).toHaveCount(0)
})

test('SCRUM-96: a request the Lead assigns from the queue joins that coordinator’s workload', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.lead)
  await page.goto('/staff/queue')
  const summit = page.getByRole('article', { name: 'Annual Partner Summit' })
  await summit.getByLabel('Coordinator email for Annual Partner Summit').fill(AISHA.email)
  await summit.getByRole('button', { name: 'Assign Annual Partner Summit' }).click()
  await expect(summit).toHaveCount(0)

  await openOversight(page)

  await expect(workloadOf(page, AISHA.full_name).getByText('Annual Partner Summit')).toBeVisible()
  await expect(activeEvent(page, 'Annual Partner Summit').getByText(AISHA.full_name)).toBeVisible()
})
