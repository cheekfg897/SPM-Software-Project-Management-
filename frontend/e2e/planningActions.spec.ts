import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { logIn } from './logIn'

/**
 * SCRUM-97, SCRUM-49, SCRUM-69, SCRUM-68: a coordinator takes events through planning from
 * their pages: sends one to safety review and sees what holds another back, confirms one the
 * Safety Officer approved and opens its registration, and marks an ended one completed
 * (ADR-0075); and rejects one whose arrangements can't be met (ADR-0093). Against the mock
 * backend, which keeps its data only until the page reloads, so the journey moves between
 * events through the app, never by reloading.
 */

/** The event's status chip, which sits just before its reference. */
function statusOf(page: Page, reference: string) {
  return page.getByText(reference, { exact: true }).locator('xpath=preceding-sibling::*[1]')
}

/** Back to Staff home through the logo, then open one of the coordinator's events by name. */
async function openFromStaffHome(page: Page, name: string, reference: string) {
  await page.getByRole('banner').getByRole('link', { name: 'ConnectSphere' }).click()
  await expect(page).toHaveURL('/staff')
  const assigned = page.getByRole('list', { name: 'Your assigned events' })
  await assigned.getByRole('link', { name: new RegExp(name) }).click()
  await expect(page).toHaveURL(`/events/${reference}`)
}

test('SCRUM-97, SCRUM-49, SCRUM-69, SCRUM-68: a coordinator takes events from approved to completed', async ({
  page,
}) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'Staff log in' }).click()
  await logIn(page, MOCK_ACCOUNTS.planningCoordinator)
  await expect(page).toHaveURL('/staff')

  // --- A settled, approved event goes to safety review ---
  await openFromStaffHome(page, 'Founders Breakfast', 'EVR-PLAN0002')
  await page.getByRole('button', { name: 'Send to safety review' }).click()
  await expect(statusOf(page, 'EVR-PLAN0002')).toHaveText('Safety review')
  await expect(page.getByRole('button', { name: 'Confirm event' })).toBeVisible()

  // --- Another is held back, and the page lists why ---
  await openFromStaffHome(page, 'Riverside Food Festival', 'EVR-PLAN0001')
  await page.getByRole('button', { name: 'Send to safety review' }).click()
  const held = page.getByRole('region', { name: 'Send to safety review' }).getByRole('alert')
  await expect(held.getByRole('listitem')).toHaveText([
    'Venue arrangement 42 is pending.',
    'Equipment request 43 has no outcome from Technical Support.',
  ])

  // --- An event the Safety Officer approved is confirmed, and its registration opened ---
  await openFromStaffHome(page, 'Harbour Lights Concert', 'EVR-PLAN0003')
  await page.getByRole('button', { name: 'Confirm event' }).click()
  await expect(statusOf(page, 'EVR-PLAN0003')).toHaveText('Confirmed')
  const registration = page.getByRole('region', { name: 'Registration settings' })
  await registration.getByRole('radiogroup', { name: 'Registration' }).getByText('Open').click()
  await registration.getByLabel('Capacity').fill('120')
  await registration.getByRole('button', { name: 'Save registration' }).click()
  await expect(registration.getByRole('status')).toHaveText('Registration is open. Capacity: 120.')

  // --- An event that has ended is marked completed ---
  await openFromStaffHome(page, 'Autumn Book Fair', 'EVR-PLAN0005')
  await page.getByRole('button', { name: 'Mark completed' }).click()
  await expect(statusOf(page, 'EVR-PLAN0005')).toHaveText('Completed')
  await expect(page.getByRole('region', { name: 'Planning' })).toHaveCount(0)
})

test('SCRUM-49: a coordinator rejects an event whose arrangements cannot be met', async ({
  page,
}) => {
  const reason = 'No venue large enough is free that week.'
  await page.goto('/')
  await page.getByRole('link', { name: 'Staff log in' }).click()
  await logIn(page, MOCK_ACCOUNTS.planningCoordinator)
  await expect(page).toHaveURL('/staff')
  await openFromStaffHome(page, 'Winter Charity Run', 'EVR-PLAN0004')
  const rejecting = page.getByRole('region', { name: 'Reject the event' })

  // --- Without a reason the backend refuses, and says so under the box ---
  await rejecting.getByRole('button', { name: 'Reject event' }).click()
  await rejecting.getByRole('button', { name: 'Yes, reject the event' }).click()
  await expect(rejecting.getByText('A reason is required to reject the event.')).toBeVisible()
  await expect(statusOf(page, 'EVR-PLAN0004')).toHaveText('Safety review')

  // --- With one, and once confirmed, the event is rejected and nothing is left to plan ---
  await rejecting.getByLabel('Reason for rejecting').fill(reason)
  await rejecting.getByRole('button', { name: 'Reject event' }).click()
  await rejecting.getByRole('button', { name: 'Yes, reject the event' }).click()
  await expect(statusOf(page, 'EVR-PLAN0004')).toHaveText('Rejected')
  await expect(page.getByRole('region', { name: 'Planning' })).toHaveCount(0)
  // --- It is the event's decision now, with the reason, and in its history ---
  await expect(page.getByRole('region', { name: 'Decision' })).toContainText(reason)
  await expect(page.getByRole('region', { name: 'History' })).toContainText(reason)
})
