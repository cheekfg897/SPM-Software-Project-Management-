import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { ROUTES } from '../src/config/routes'
import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/**
 * SCRUM-53: an Attendee withdraws from an event on My events, after confirming, and the
 * catalogue offers the place again. The mock attendee holds Startup Pitch Night (7 Oct).
 */

const PITCH_NIGHT = 'Startup Pitch Night'

function card(page: Page, eventName: string) {
  return page.getByRole('article').filter({ has: page.getByRole('heading', { name: eventName }) })
}

test('an attendee withdraws from an event and the catalogue offers the place again', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.attendee)
  await page.goto(ROUTES.MY_EVENTS)

  const pitchNight = card(page, PITCH_NIGHT)
  await expect(pitchNight.getByText('Registered')).toBeVisible()
  await pitchNight.getByRole('button', { name: `Withdraw from ${PITCH_NIGHT}` }).click()
  await pitchNight.getByRole('button', { name: 'Yes, withdraw' }).click()
  await expect(pitchNight.getByText('Withdrawn')).toBeVisible()

  await page.getByRole('banner').getByRole('link', { name: 'Events', exact: true }).click()
  await expect(page).toHaveURL(ROUTES.EVENTS)
  await expect(card(page, PITCH_NIGHT).getByRole('button', { name: 'Register' })).toBeVisible()
})
