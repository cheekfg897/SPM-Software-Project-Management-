import { StatusChip } from '@/components/ui'

import { OUTCOME_ACTION_LABELS } from '../constants'
import type { SafetyOutcome } from '../constants'
import { useLatestOutcome } from '../hooks'

/**
 * Where each outcome leaves the event: an approval keeps it in Safety Review for the coordinator
 * to confirm (SCRUM-98 AC5); Reject and Request Changes send it back to Approved, the planning
 * stage (AC6, ADR-0047 decision 17).
 */
const NEXT_STEP: Record<SafetyOutcome, string> = {
  approved: 'It stays in Safety review until its coordinator confirms it.',
  rejected: 'It goes back to its coordinator at Approved, the planning stage.',
  changes_requested: 'It goes back to its coordinator at Approved, the planning stage.',
}

/**
 * What the Safety Officer recorded last, once the event has left the list: the outcome, the
 * status the backend says the event is now in, and what happens next (SCRUM-98 AC8: the
 * coordinator is told).
 */
export function LatestOutcomeNotice() {
  const latest = useLatestOutcome()
  if (latest === undefined) {
    return null
  }
  const { input, recorded } = latest

  return (
    <div role="status" className="border-success/30 bg-success/10 rounded-2xl border px-5 py-4">
      <p className="text-ink font-medium">
        Safety check recorded for {recorded.name}: {OUTCOME_ACTION_LABELS[input.outcome]}.
      </p>
      <p className="text-ink-muted mt-2 flex items-center gap-2 text-sm">
        Status now <StatusChip status={recorded.status} />
      </p>
      <p className="text-ink-muted mt-2 text-sm">{NEXT_STEP[input.outcome]}</p>
      <p className="text-ink-muted text-sm">Its coordinator has been notified.</p>
    </div>
  )
}
