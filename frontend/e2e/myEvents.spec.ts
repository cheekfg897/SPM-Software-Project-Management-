import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { signInAs } from './signInAs'

/**
 * SCRUM-24 AC7 and SCRUM-52 AC5: an Attendee's own events, against the mock (docs/adr/0044).
 * The mock's "now" is Monday 5 October 2026, so the same events show on every run.
 */

function card(page: Page, eventName: string) {
  return page.getByRole('article').filter({ has: page.getByRole('heading', { name: eventName }) })
}

test('a new attendee signs up, registers, and finds the event in My events', async ({ page }) => {
  await page.goto('/signup')
  await page.getByLabel('Full name').fill('Priya Nair')
  await page.getByLabel('Email').fill('priya.events@example.com')
  await page.getByLabel('Password').fill('Password123')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL('/events')

  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'My events' })
    .click()
  await expect(page).toHaveURL('/my-events')
  await expect(page.getByText('You have no upcoming events.')).toBeVisible()

  await page.getByRole('link', { name: 'Browse events' }).click()
  await expect(page).toHaveURL('/events')
  const jazz = card(page, 'Jazz by the Bay')
  await jazz.getByRole('button', { name: 'Register' }).click()
  await expect(jazz.getByText("You're registered")).toBeVisible()

  await jazz.getByRole('link', { name: 'View in My events' }).click()
  await expect(page).toHaveURL('/my-events')
  const registered = card(page, 'Jazz by the Bay')
  await expect(registered.getByText('7:30 pm – 10:00 pm')).toBeVisible()
  await expect(registered.getByText('Confirmed')).toBeVisible()
})

test('an attendee looks back at past events, and sees one that was cancelled', async ({ page }) => {
  await signInAs(page, MOCK_ACCOUNTS.attendee)
  await page.goto('/my-events')
  await expect(card(page, 'Harbour Lights Run').getByText('Cancelled')).toBeVisible()

  await page
    .getByRole('radiogroup', { name: 'Which events' })
    .getByText('Past', { exact: true })
    .click()

  await expect(page).toHaveURL('/my-events?when=past')
  await expect(card(page, 'Orchid Show Opening Night').getByText('Completed')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Startup Pitch Night' })).toHaveCount(0)
})
