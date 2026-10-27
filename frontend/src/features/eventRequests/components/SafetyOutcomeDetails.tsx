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

/**
 * The reason, and on a Reject or Request Changes what the officer named to rework (SCRUM-99 AC4):
 * with nothing named, the reason is shown on the event itself as "Flagged by the Safety Officer";
 * otherwise each flagged arrangement shows it beside itself, and this says how much was named.
 */
function ReworkReason({ outcome }: { outcome: SafetyCheckOutcome }) {
  if (outcome.reason === null) {
    return null
  }
  const namedNothing = outcome.flagged_arrangement_count === 0 && outcome.reopened_line_count === 0
  if (outcome.outcome === 'approved') {
    return <p className="text-ink mt-2">{outcome.reason}</p>
  }
  if (namedNothing) {
    return <p className="text-ink mt-2">Flagged by the Safety Officer: {outcome.reason}</p>
  }
  return (
    <>
      <p className="text-ink mt-2">{outcome.reason}</p>
      <p className="text-ink-muted mt-1">
        Named to rework: {counted(outcome.flagged_arrangement_count, 'venue arrangement')} and{' '}
        {counted(outcome.reopened_line_count, 'equipment line')}.
      </p>
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
