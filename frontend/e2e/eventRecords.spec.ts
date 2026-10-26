import { expect, test } from '@playwright/test'

import { MOCK_ACCOUNTS } from '../src/mocks/fixtures/accounts'

import { logIn } from './logIn'
import { signInAs } from './signInAs'

/**
 * SCRUM-24 AC2, AC9: a coordinator finds their events on Staff home and works on one; an
 * organiser opens a request to see where it stands (ADR-0056). Against the mock backend.
 */

test('SCRUM-24: a coordinator logs in, opens an assigned event and goes on to its venue requests', async ({
  page,
}) => {
  await page.goto('/staff/login')

  await logIn(page, MOCK_ACCOUNTS.coordinator)

  await expect(page).toHaveURL('/staff')
  const assigned = page.getByRole('list', { name: 'Your assigned events' })
  // In mock mode the app mounts once the mock worker starts: wait for a row before reading them.
  await expect(assigned.getByRole('heading', { name: 'Partner Summit' })).toBeVisible()
  await expect(assigned.getByRole('listitem')).toHaveCount(5)

  await assigned.getByRole('link', { name: /Harbourfront Careers Fair/ }).click()

  await expect(page).toHaveURL('/events/EVR-BOOK0101')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Harbourfront Careers Fair' }),
  ).toBeVisible()
  await expect(page.getByText('Step-free access')).toBeVisible()

  await page.getByRole('link', { name: 'Venue requests' }).click()

  await expect(page).toHaveURL('/events/EVR-BOOK0101/venue-requests')
  await expect(page.getByRole('heading', { level: 1, name: 'Venue requests' })).toBeVisible()
})

test("SCRUM-24: an organiser opens a request and sees the coordinator's open question", async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.organiser)
  await page.goto('/organiser')

  const list = page.getByRole('list', { name: 'Your event requests' })
  await list.getByRole('link', { name: /Customer Roadshow/ }).click()

  await expect(page).toHaveURL('/organiser/requests/EVR-B6YF2K8V')
  await expect(page.getByRole('heading', { level: 1, name: 'Customer Roadshow' })).toBeVisible()
  await expect(page.getByText('Awaiting clarification')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Coordinator' })).toContainText('Chloe Lim')
  await expect(page.getByText('Waiting for an answer.')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Venue requests' })).toHaveCount(0)
})

test('SCRUM-24 AC10: an organiser opens their confirmed events and sees everything on the record', async ({
  page,
}) => {
  await signInAs(page, MOCK_ACCOUNTS.otherOrganiser)
  await page.goto('/organiser')

  const list = page.getByRole('list', { name: 'Your event requests' })
  await list.getByRole('link', { name: /Harbour Gala/ }).click()

  await expect(page).toHaveURL('/organiser/requests/EVR-BOOK0112')
  const venues = page.getByRole('region', { name: 'Venue arrangements' })
  // Every arrangement, the withdrawn one too, each with its status and what was asked for.
  await expect(venues.getByRole('listitem')).toHaveCount(3)
  await expect(venues).toContainText('Gala dinner · 10 guests · Banquet')
  await expect(venues).toContainText('Venue Staff: Booked for the dinner.')
  await expect(venues).toContainText('Withdrawn')
  await expect(page.getByRole('region', { name: 'Planning notes' })).toContainText(
    'No planning notes yet.',
  )

  await page.goto('/organiser')
  await list.getByRole('link', { name: /Year-End Town Hall/ }).click()

  await expect(page).toHaveURL('/organiser/requests/EVR-BOOK0102')
  const safety = page.getByRole('region', { name: 'Safety check' })
  await expect(safety).toContainText('Approved')
  await expect(safety).toContainText('Both fire exits are clear.')
  await expect(safety).toContainText('Recorded by Sana Iyer, 4 Oct, 2:00 pm')
})
