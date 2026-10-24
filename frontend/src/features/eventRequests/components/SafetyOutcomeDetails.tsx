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

/**
 * The Safety Officer's outcome on the event's current check: the outcome, the reason, a note
 * against each checklist item in SCRUM-98 AC2's order, and who recorded it when (ADR-0095).
 */
export function SafetyOutcomeDetails({ outcome }: { outcome: SafetyCheckOutcome | null }) {
  if (outcome === null) {
    return <EmptyState message={NO_OUTCOME_YET} />
  }
  return (
    <div className="border-line/60 bg-surface/50 rounded-2xl border p-5">
      <p className="text-ink font-semibold">{OUTCOME_LABELS[outcome.outcome]}</p>
      {outcome.reason !== null && <p className="text-ink mt-2">{outcome.reason}</p>}
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
