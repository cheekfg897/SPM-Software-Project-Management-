import type { ReassessmentFlag } from '../api'
import { REASSESSMENT_KIND_LABELS } from '../constants'

/**
 * Each reason a change to the event flagged a booking, with its kind, oldest first (SCRUM-33
 * AC6, SCRUM-59 AC1). The coordinator's notice of a flagged arrangement and Venue Staff's flagged
 * list both show them.
 */
export function ChangeFlagReasons({ flags }: { flags: ReassessmentFlag[] }) {
  return (
    <ul aria-label="Why a change to the event flagged it" className="text-ink space-y-1">
      {/* By place: two changes may give the same reason. */}
      {flags.map((flag, index) => (
        <li key={index}>
          {REASSESSMENT_KIND_LABELS[flag.kind]}: {flag.reason}
        </li>
      ))}
    </ul>
  )
}
