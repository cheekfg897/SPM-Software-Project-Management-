import type { EventHistoryEntry } from '@/features/eventRequests/api'

import { MOCK_EVENT_HISTORY } from './eventRecordSectionFixtures'

/**
 * Each event's history as it stands, edits included, oldest first: what the history route
 * answers (eventRecordSections.ts) and what the organiser's record reads the current safety
 * check from (eventRequests.ts). Kept apart from both, so neither imports the other.
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

/** How many ids a check's history entry named, as the backend counts them (SCRUM-99). */
function namedIn(ids: unknown): number {
  return Array.isArray(ids) ? ids.length : 0
}

/**
 * The outcome on the event's current safety check, with its checklist, reason, officer and time,
 * or null, as the backend's _safety_outcome_of reads it: the newest entry that opens, settles or
 * withdraws a check decides (ADR-0047, ADR-0095).
 */
export function currentSafetyCheckOf(reference: string) {
  const checks = historyOf(reference).filter((entry) => SAFETY_CHECK_KINDS.includes(entry.kind))
  const latest = checks.at(-1)
  if (latest === undefined || latest.kind !== 'safety_outcome_recorded') {
    return null
  }
  return {
    outcome: latest.details.outcome,
    checklist: latest.details.checklist ?? {},
    reason: latest.details.reason ?? null,
    recorded_by: latest.actor_name,
    recorded_at: latest.occurred_at,
    // What the officer named to rework (SCRUM-99 AC4); none on a check that named nothing.
    flagged_arrangement_count: namedIn(latest.details.flagged_arrangement_ids),
    reopened_line_count: namedIn(latest.details.reopened_line_ids),
  }
}
