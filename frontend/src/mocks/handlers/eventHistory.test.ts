import { fetchEventHistory } from '@/features/eventRequests/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import { addToHistory } from './eventRecordSections'

/**
 * The mock of an event's history (GET /api/events/requests/<reference>/history), pinned to
 * what the backend sends (SCRUM-33 AC4, AC5; ADR-0025): who may read it, and what an organiser
 * is not shown. The integration tests check the same shape against the running backend.
 */

/** Chloe's, under review, in the mock organiser's organisation. */
const CHLOES = 'EVR-7K2M9QXA'
/** Marcus's, approved, in the mock organiser's organisation: equipment and a safety check. */
const MARCUSES = 'EVR-W9CR5E7M'
const A_DRAFT = 'EVR-3HD8PL2W'
const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event request not found.' }
/** INTERNAL_ONLY_KINDS in events/services.py on main, written out. */
const INTERNAL_ONLY_KINDS = [
  'equipment_reserved',
  'equipment_outcome_recorded',
  'safety_outcome_recorded',
  'venue_preparation_updated',
  'equipment_preparation_updated',
  'alternative_venue_needed',
  'safety_approval_withdrawn',
]

function signInAs(account: MockAccount | null) {
  sendRequestsAs(account === null ? null : mockTokenFor(account))
}

/** Add an entry of `kind` to Partner Summit's history, as the backend would write it. */
function recordOnPartnerSummit(kind: string) {
  addToHistory(CHLOES, [
    { kind, occurred_at: '2026-10-09T09:00:00+08:00', actor_name: 'Vera Goh', details: {} },
  ])
}

async function kindsSeenBy(account: MockAccount, reference: string) {
  signInAs(account)
  const { history } = await fetchEventHistory(reference)
  return history.map((entry) => entry.kind)
}

describe('SCRUM-33 mock of an event history: what each viewer sees', () => {
  it('gives the assigned coordinator every entry, oldest first, names and no ids', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const { history } = await fetchEventHistory(CHLOES)

    expect(history).toHaveLength(4)
    expect(history[0]).toEqual({
      kind: 'coordinator_assigned',
      occurred_at: '2026-10-06T14:00:00+08:00',
      actor_name: 'Leon Goh',
      details: { coordinator_name: 'Chloe Lim' },
    })
    expect(history.map((entry) => entry.details.field)).toEqual([
      undefined,
      undefined,
      'internal_planning_notes',
      'expected_attendance',
    ])
  })

  it('leaves the internal planning notes out of an organiser copy (ADR-0025)', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    const { history } = await fetchEventHistory(CHLOES)

    expect(history.map((entry) => entry.details.field)).toEqual([
      undefined,
      undefined,
      'expected_attendance',
    ])
  })

  it('leaves equipment and the safety outcome out of an organiser copy, and keeps the rest', async () => {
    expect(await kindsSeenBy(MOCK_ACCOUNTS.organiser, MARCUSES)).toEqual([
      'coordinator_assigned',
      'decision_recorded',
      'safety_review_requested',
    ])
  })

  it.each([
    ['Technical Support', MOCK_ACCOUNTS.technicalSupport],
    ['the Lead', MOCK_ACCOUNTS.lead],
    ['the Safety Officer', MOCK_ACCOUNTS.safetyOfficer],
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
  ])('gives %s every entry of any event', async (_, account) => {
    expect(await kindsSeenBy(account, MARCUSES)).toEqual([
      'coordinator_assigned',
      'decision_recorded',
      'equipment_reserved',
      'equipment_outcome_recorded',
      'safety_review_requested',
      'safety_outcome_recorded',
    ])
  })

  it.each(INTERNAL_ONLY_KINDS)(
    'keeps %s entries from an organiser but not from staff',
    async (kind) => {
      recordOnPartnerSummit(kind)

      expect(await kindsSeenBy(MOCK_ACCOUNTS.organiser, CHLOES)).not.toContain(kind)
      expect(await kindsSeenBy(MOCK_ACCOUNTS.coordinator, CHLOES)).toContain(kind)
    },
  )

  it('shows an organiser a kind the backend does not keep internal, such as an expired hold', async () => {
    recordOnPartnerSummit('venue_hold_expired')

    expect(await kindsSeenBy(MOCK_ACCOUNTS.organiser, CHLOES)).toContain('venue_hold_expired')
  })

  it('gives an event with nothing recorded yet an empty history', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    expect(await fetchEventHistory('EVR-Q4ZT6N1B')).toEqual({ history: [] })
  })
})

describe('SCRUM-33 mock of an event history: who is refused', () => {
  it("answers a coordinator another coordinator's event as not found", async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    expect(await refusal(fetchEventHistory(MARCUSES))).toMatchObject(NOT_FOUND)
  })

  it("answers an organiser another organisation's event as not found", async () => {
    signInAs(MOCK_ACCOUNTS.otherOrganiser)

    expect(await refusal(fetchEventHistory(CHLOES))).toMatchObject(NOT_FOUND)
  })

  it('answers staff a draft as not found (ADR-0024)', async () => {
    signInAs(MOCK_ACCOUNTS.lead)

    expect(await refusal(fetchEventHistory(A_DRAFT))).toMatchObject(NOT_FOUND)
  })

  it('refuses an organiser with no organisation, an attendee and a visitor', async () => {
    signInAs(MOCK_ACCOUNTS.unlinkedOrganiser)
    const unlinked = await refusal(fetchEventHistory(CHLOES))
    signInAs(MOCK_ACCOUNTS.attendee)
    const attendee = await refusal(fetchEventHistory(CHLOES))
    signInAs(null)
    const visitor = await refusal(fetchEventHistory(CHLOES))

    expect(unlinked).toMatchObject({ status: 403, code: 'organiser_without_organisation' })
    expect(attendee).toMatchObject({ status: 403, code: 'authorization_error' })
    expect(visitor).toMatchObject({ status: 401, code: 'authentication_error' })
  })
})
