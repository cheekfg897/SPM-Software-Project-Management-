import { EmptyState } from '@/components/ui'
import { CHECKLIST } from '@/features/safety/constants'
import type { SafetyOutcome } from '@/features/safety/constants'
import { attributed } from '@/lib/attributed'

import type { SafetyCheckOutcome } from '../api'

const NO_OUTCOME_YET = "The Safety Officer hasn't recorded an outcome on the current check."

/** Each outcome in words (SCRUM-98 AC1). */
const OUTCOME_LABELS: Record<SafetyOutcome, string> = {
  approved: 'Approved',
  rejected: 'Rejected',
  changes_requested: 'Changes requested',
}

/** e.g. "1 venue arrangement" or "2 equipment lines". */
function counted(count: number, thing: string): string {
  return `${String(count)} ${thing}${count === 1 ? '' : 's'}`
}

/** What the outcome named, leaving out what it named none of: "1 venue arrangement and 2 equipment lines". */
function namedToRework(outcome: SafetyCheckOutcome): string {
  const named = []
  if (outcome.flagged_arrangement_count > 0) {
    named.push(counted(outcome.flagged_arrangement_count, 'venue arrangement'))
  }
  if (outcome.reopened_line_count > 0) {
    named.push(counted(outcome.reopened_line_count, 'equipment line'))
  }
  return named.join(' and ')
}

/**
 * The reason, and on a Reject or Request Changes what the officer named to rework (SCRUM-99 AC4).
 * Each flagged arrangement shows "Flagged by the Safety Officer: <reason>" beside itself; with no
 * arrangement flagged, the reason is shown on the event itself in those words (ADR-0113).
 */
function ReworkReason({ outcome }: { outcome: SafetyCheckOutcome }) {
  if (outcome.reason === null) {
    return null
  }
  if (outcome.outcome === 'approved') {
    return <p className="text-ink mt-2">{outcome.reason}</p>
  }
  const named = namedToRework(outcome)
  const reason =
    outcome.flagged_arrangement_count === 0
      ? `Flagged by the Safety Officer: ${outcome.reason}`
      : outcome.reason
  return (
    <>
      <p className="text-ink mt-2">{reason}</p>
      {named !== '' && <p className="text-ink-muted mt-1">Named to rework: {named}.</p>}
    </>
  )
}

/**
 * The Safety Officer's outcome on the event's current check: the outcome, the reason and what it
 * named to rework, a note against each checklist item in SCRUM-98 AC2's order, and who recorded it
 * when (ADR-0095).
 */
export function SafetyOutcomeDetails({ outcome }: { outcome: SafetyCheckOutcome | null }) {
  if (outcome === null) {
    return <EmptyState message={NO_OUTCOME_YET} />
  }
  return (
    <div className="border-line/60 bg-surface/50 rounded-2xl border p-5">
      <p className="text-ink font-semibold">{OUTCOME_LABELS[outcome.outcome]}</p>
      <ReworkReason outcome={outcome} />
      <dl className="mt-4 space-y-3">
        {CHECKLIST.map(({ item, label }) => (
          <div key={item}>
            <dt className="text-ink-muted text-sm">{label}</dt>
            <dd className="text-ink">{outcome.checklist[item]}</dd>
          </div>
        ))}
      </dl>
      <p className="text-ink-faint mt-4 text-sm">
        {attributed('Recorded', outcome.recorded_by, outcome.recorded_at)}
      </p>
    </div>
  )
}
