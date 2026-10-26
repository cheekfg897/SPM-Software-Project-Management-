import { expect, test } from '@playwright/test'

import { myEventPath, ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/**
 * SCRUM-24 AC11: an Attendee opens one of their events from My events, sees where it is, and
 * withdraws there (SCRUM-53), then finds it withdrawn back on My events. The mock attendee holds
 * Startup Pitch Night (7 Oct) at The Projector.
 */

const PITCH_NIGHT = 'Startup Pitch Night'
const PITCH_NIGHT_REFERENCE = 'EVR-MOCK0005'

test('an attendee opens their event from My events and withdraws from it there', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.attendee)
  await page.goto(ROUTES.MY_EVENTS)

  await page.getByRole('link', { name: PITCH_NIGHT }).click()
  await expect(page).toHaveURL(myEventPath(PITCH_NIGHT_REFERENCE))
  await expect(page.getByRole('heading', { level: 1, name: PITCH_NIGHT })).toBeVisible()
  await expect(page.getByText('The Projector, Golden Mile Tower')).toBeVisible()
  await expect(page.getByText('100 Beach Road, Level 5')).toBeVisible()

  await page.getByRole('button', { name: `Withdraw from ${PITCH_NIGHT}` }).click()
  await page.getByRole('button', { name: 'Yes, withdraw' }).click()
  await expect(page.getByText('Withdrawn')).toBeVisible()
  await expect(page.getByRole('button', { name: `Withdraw from ${PITCH_NIGHT}` })).toHaveCount(0)

  await page.getByRole('link', { name: 'Back to My events' }).click()
  await expect(page).toHaveURL(ROUTES.MY_EVENTS)
  const card = page
    .getByRole('article')
    .filter({ has: page.getByRole('heading', { name: PITCH_NIGHT }) })
  await expect(card.getByText('Withdrawn')).toBeVisible()
})

test('an attendee opens an event a change sent back to planning, and is told it may change', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.attendee)
  await page.goto(ROUTES.MY_EVENTS)

  await page.getByRole('link', { name: 'Rooftop Film Night' }).click()
  await expect(page).toHaveURL(myEventPath('EVR-MOCK0903'))
  await expect(page.getByRole('heading', { level: 1, name: 'Rooftop Film Night' })).toBeVisible()
  await expect(
    page.getByText(
      'This event’s arrangements are being reviewed and may change. You will be notified of any change.',
    ),
  ).toBeVisible()
  await expect(page.getByText('Approved')).toBeVisible()
})
