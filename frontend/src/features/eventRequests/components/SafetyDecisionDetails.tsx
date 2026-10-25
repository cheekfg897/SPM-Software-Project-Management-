import { attributed } from '@/lib/attributed'

import type { OrganiserSafetyDecision } from '../api'
import { humanise } from '../humanise'

/** The Safety Officer's final decision and when, never who or their notes (SCRUM-49 AC11). */
export function SafetyDecisionDetails({ decision }: { decision: OrganiserSafetyDecision }) {
  return (
    <div className="border-line/60 bg-surface/50 rounded-2xl border p-5">
      <p className="text-ink font-semibold">{humanise(decision.outcome)}</p>
      <p className="text-ink-faint mt-2 text-sm">
        {attributed('Decided', null, decision.decided_at)}
      </p>
    </div>
  )
}
