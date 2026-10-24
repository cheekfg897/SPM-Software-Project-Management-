import { PREPARATION_STATUS_LABELS } from '@/config/preparation'
import type { Preparation } from '@/config/preparation'

/**
 * A booking's or a reservation's preparation as the backend last saved it (SCRUM-84 AC2, SCRUM-85
 * AC2): on Venue Staff's pages and on the read-only event record (ADR-0095).
 */
export function PreparationSummary({ preparation }: { preparation: Preparation }) {
  return (
    <>
      <p className="text-ink-muted">
        Preparation: {PREPARATION_STATUS_LABELS[preparation.preparation_status]}
      </p>
      {preparation.preparation_notes !== null && (
        <p className="text-ink-muted">Preparation notes: {preparation.preparation_notes}</p>
      )}
    </>
  )
}
