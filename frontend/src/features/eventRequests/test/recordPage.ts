import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import type { EventRequestStatus } from '@/config/eventStatus'
import { fetchEventRequest } from '@/features/eventRequests/api'
import { mockTokenFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { server } from '@/mocks/server'
import { sendRequestsAs } from '@/test/sendRequestsAs'

/** The page region named `name`, once the record has loaded. */
export function findRegion(name: string) {
  return screen.findByRole('region', { name })
}

/** The record page's status chip, which sits just before the reference. */
export function statusShownFor(reference: string) {
  return screen.getByText(reference).previousElementSibling?.textContent
}

/**
 * Answer the record of `reference` as the mock would send it to `account`, but in `status`, so
 * a page can be tested in a status the mock's data never reaches.
 */
export async function serveRecordInStatus(
  account: MockAccount,
  reference: string,
  status: EventRequestStatus,
) {
  sendRequestsAs(mockTokenFor(account))
  const record = await fetchEventRequest(reference)
  server.use(
    http.get(`/api/events/requests/${reference}`, () => HttpResponse.json({ ...record, status })),
  )
}
