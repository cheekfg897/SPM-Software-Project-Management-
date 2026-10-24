import { attributed } from '@/lib/attributed'

import type { Decision } from '../api'

interface DecisionStyle {
  label: string
  /** Theme-token class for the outcome's colour. */
  tone: string
}

const DECISION_STYLE: Record<Decision['outcome'], DecisionStyle> = {
  approved: { label: 'Approved', tone: 'text-success' },
  rejected: { label: 'Rejected', tone: 'text-danger' },
}

/** The coordinator's current ruling, its reason and who made it (SCRUM-31 AC9, ADR-0028). */
export function DecisionDetails({ decision }: { decision: Decision }) {
  const { label, tone } = DECISION_STYLE[decision.outcome]
  return (
    <div className="border-line/60 bg-surface/50 rounded-2xl border p-5">
      <p className={`font-semibold ${tone}`}>{label}</p>
      {decision.reason !== null && <p className="text-ink mt-2">{decision.reason}</p>}
      <p className="text-ink-faint mt-2 text-sm">
        {attributed('Decided', decision.decided_by, decision.decided_at)}
      </p>
    </div>
  )
}
