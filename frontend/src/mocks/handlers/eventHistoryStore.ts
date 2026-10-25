import type { EventHistoryEntry } from '@/features/eventRequests/api'

import { MOCK_EVENT_HISTORY } from './eventRecordSectionFixtures'

/**
 * Each event's history as it stands, edits included, oldest first: what the history route
 * answers (eventRecordSections.ts) and what the record reads the Safety Officer's final decision
 * from (eventRequests.ts). Kept apart from both, so neither imports the other.
 */

/** The kinds that open, settle or withdraw a safety check, as the backend's SAFETY_CHECK_KINDS. */
const SAFETY_CHECK_KINDS: readonly string[] = [
  'safety_review_requested',
  'safety_outcome_recorded',
  'safety_approval_withdrawn',
]

let storedHistory: Record<string, EventHistoryEntry[]> = {}

/** Put the history back as the fixture has it. Runs after every test. */
export function resetMockEventHistory(): void {
  storedHistory = {}
  for (const [reference, entries] of Object.entries(MOCK_EVENT_HISTORY)) {
    storedHistory[reference] = [...entries]
  }
}
resetMockEventHistory()

/** Add `entries` to the end of an event's history, as the backend writes them. */
export function addToHistory(reference: string, entries: EventHistoryEntry[]): void {
  storedHistory[reference] = [...(storedHistory[reference] ?? []), ...entries]
}

/** The event's history, oldest first. */
export function historyOf(reference: string): EventHistoryEntry[] {
  return storedHistory[reference] ?? []
}

/**
 * The outcome on the event's current safety check and when it was made, or null, as the
 * backend's _current_safety_outcome_entry reads it: the newest entry that opens, settles or
 * withdraws a check decides (ADR-0047).
 */
export function currentSafetyOutcomeOf(reference: string) {
  const checks = historyOf(reference).filter((entry) => SAFETY_CHECK_KINDS.includes(entry.kind))
  const latest = checks.at(-1)
  if (latest === undefined || latest.kind !== 'safety_outcome_recorded') {
    return null
  }
  return { outcome: latest.details.outcome, decided_at: latest.occurred_at }
}
