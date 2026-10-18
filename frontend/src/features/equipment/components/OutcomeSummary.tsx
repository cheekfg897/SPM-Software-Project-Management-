import { attributed } from '@/lib/attributed'

import type { EquipmentLine } from '../api'
import { hasOutcome } from '../lineOutcome'
import type { ReviewedLine } from '../lineOutcome'

/** e.g. "6 of 10 provided, short by 4", or "4 of 4 provided" when nothing is short. */
function providedText(line: ReviewedLine): string {
  const provided = `${line.provided_quantity} of ${line.quantity} provided`
  if (line.shortfall === 0) {
    return provided
  }
  return `${provided}, short by ${line.shortfall}`
}

/**
 * Technical Support's outcome for one line, as staff see it (SCRUM-48 AC1, AC2, AC5): how many
 * will be provided and the shortfall the backend sent, the note, and who reviewed it when.
 */
export function OutcomeSummary({ line }: { line: EquipmentLine }) {
  if (!hasOutcome(line)) {
    return <span className="text-ink-faint">Not reviewed yet</span>
  }
  return (
    <div className="space-y-1">
      <p className="text-ink">{providedText(line)}</p>
      {line.outcome_note !== null && <p className="text-ink-muted">{line.outcome_note}</p>}
      <p className="text-ink-faint text-xs">
        {attributed('Reviewed', line.reviewed_by, line.reviewed_at)}
      </p>
    </div>
  )
}
