import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { logIn } from './logIn'

/**
 * SCRUM-97, SCRUM-49, SCRUM-69, SCRUM-68: a coordinator takes events through planning from
 * their pages: sends one to safety review and sees what holds another back, confirms one the
 * Safety Officer approved and opens its registration, and marks an ended one completed
 * (ADR-0075); records and removes a withdrawal cut-off (ADR-0115); and rejects one whose
 * arrangements can't be met (ADR-0093). Against the mock
 * backend, which keeps its data only until the page reloads, so the journey moves between
 * events through the app, never by reloading.
 */

/** How the saved registration card ends when the event has no withdrawal cut-off. */
const NO_CUT_OFF = 'No withdrawal cut-off: withdrawals close when the event starts.'

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

/** Log in as Hana, the planning coordinator, through the staff log-in. */
async function logInAsHana(page: Page) {
  await page.goto('/')
  await page.getByRole('link', { name: 'Staff log in' }).click()
  await logIn(page, MOCK_ACCOUNTS.planningCoordinator)
  await expect(page).toHaveURL('/staff')
}

test('SCRUM-97, SCRUM-49, SCRUM-69, SCRUM-68: a coordinator takes events from approved to completed', async ({
  page,
}) => {
  await logInAsHana(page)

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
  await expect(registration.getByRole('status')).toHaveText(
    `Registration is open. Capacity: 120. ${NO_CUT_OFF}`,
  )

  // --- An event that has ended is marked completed ---
  await openFromStaffHome(page, 'Autumn Book Fair', 'EVR-PLAN0005')
  await page.getByRole('button', { name: 'Mark completed' }).click()
  await expect(statusOf(page, 'EVR-PLAN0005')).toHaveText('Completed')
  await expect(page.getByRole('region', { name: 'Planning' })).toHaveCount(0)
})

test('SCRUM-69: a coordinator records a withdrawal cut-off before the start, and removes it', async ({
  page,
}) => {
  await logInAsHana(page)
  // Weekend Coding Camp starts on 4 Oct at 10:00 am; its organiser asked for registration.
  await openFromStaffHome(page, 'Weekend Coding Camp', 'EVR-PLAN0006')
  const registration = page.getByRole('region', { name: 'Registration settings' })
  const cutOff = registration.getByLabel('Withdrawal cut-off')
  const save = registration.getByRole('button', { name: 'Save registration' })

  // --- A cut-off at the start is refused, in the backend's words under the box ---
  await registration.getByLabel('Capacity').fill('40')
  await cutOff.fill('2026-10-04T10:00')
  await save.click()
  await expect(
    registration.getByText('The withdrawal cut-off must be before the event starts.'),
  ).toBeVisible()
  await expect(cutOff).toBeFocused()

  // --- The evening before is recorded, and the history says who recorded it ---
  await cutOff.fill('2026-10-03T18:00')
  await save.click()
  await expect(registration.getByRole('status')).toHaveText(
    'Registration is open. Capacity: 40. Withdrawal cut-off: 3 Oct, 6:00 pm.',
  )
  const recorded = page
    .getByRole('region', { name: 'History' })
    .getByRole('listitem')
    .filter({ hasText: 'Withdrawal cut-off changed' })
  await expect(recorded).toContainText('Hana Yusof')
  await expect(recorded).toContainText('3 Oct, 6:00 pm')

  // --- Removed, withdrawals close when the event starts again ---
  await registration.getByRole('checkbox', { name: 'Remove the cut-off' }).check()
  await expect(cutOff).toBeDisabled()
  await save.click()
  await expect(registration.getByRole('status')).toHaveText(
    `Registration is open. Capacity: 40. ${NO_CUT_OFF}`,
  )
})

test('SCRUM-49: a coordinator rejects an event whose arrangements cannot be met', async ({
  page,
}) => {
  const reason = 'No venue large enough is free that week.'
  await logInAsHana(page)
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
