import { PreparationSummary } from '@/components/preparation/PreparationSummary'
import { EmptyState } from '@/components/ui'
import { EQUIPMENT_LINE_STATUS_LABELS } from '@/features/equipment/constants'
import type { SafetyReviewEquipment } from '@/features/safety/api'
import { attributed } from '@/lib/attributed'
import { formatShortDate, formatTimeRange } from '@/lib/formatDate'

import type { RecordEquipmentLine, StaffReservation } from '../api'

const NONE_REQUESTED = 'No equipment has been requested for this event.'
const NONE_RESERVED = 'No equipment is reserved for this event yet.'

/** Whether the backend sent who reviewed the line, as the organiser's record does (ADR-0104). */
function isReviewedLine(line: SafetyReviewEquipment): line is RecordEquipmentLine {
  return 'reviewed_by' in line
}

/** Technical Support's answer: the outcome, with how many they will provide once decided. */
function outcomeOf(line: SafetyReviewEquipment): string {
  const label = EQUIPMENT_LINE_STATUS_LABELS[line.status]
  if (line.provided_quantity === null) {
    return label
  }
  return `${label}, ${String(line.provided_quantity)} provided`
}

function RequestedEquipment({ lines }: { lines: SafetyReviewEquipment[] }) {
  if (lines.length === 0) {
    return <EmptyState message={NONE_REQUESTED} />
  }
  return (
    <ul aria-label="Equipment requested" className="space-y-3">
      {lines.map((line) => (
        <li
          key={line.equipment_type_name}
          className="border-line/60 bg-surface/50 rounded-2xl border p-5"
        >
          <p className="text-ink font-medium">
            {line.equipment_type_name} · {line.quantity} requested
          </p>
          {line.notes !== null && <p className="text-ink-muted">Note: {line.notes}</p>}
          <p className="text-ink mt-2">Technical Support: {outcomeOf(line)}</p>
          {line.outcome_note !== null && <p className="text-ink-muted">{line.outcome_note}</p>}
          {isReviewedLine(line) && line.reviewed_at !== null && (
            <p className="text-ink-faint mt-1 text-sm">
              {attributed('Reviewed', line.reviewed_by, line.reviewed_at)}
            </p>
          )}
        </li>
      ))}
    </ul>
  )
}

function ReservedEquipment({ reservations }: { reservations: StaffReservation[] }) {
  if (reservations.length === 0) {
    return <EmptyState message={NONE_RESERVED} />
  }
  return (
    <ul aria-label="Equipment reserved" className="space-y-3">
      {reservations.map((reservation, index) => (
        // The backend sends no ids on the record (ADR-0095), and the list never reorders.
        <li key={index} className="border-line/60 bg-surface/50 rounded-2xl border p-5">
          <p className="text-ink font-medium">
            {reservation.equipment_type_name} · {reservation.quantity} reserved
          </p>
          <p className="text-ink-muted text-sm">
            {formatShortDate(reservation.starts_at)},{' '}
            {formatTimeRange(reservation.starts_at, reservation.ends_at)}
            {reservation.reserved_by !== null && ` · by ${reservation.reserved_by}`}
          </p>
          <PreparationSummary preparation={reservation} />
        </li>
      ))}
    </ul>
  )
}

interface EquipmentOnRecordProps {
  lines: SafetyReviewEquipment[]
  reservations: StaffReservation[]
}

/**
 * The event's equipment: what was requested, with Technical Support's outcome (and who reviewed
 * it, when the backend sends that, ADR-0104), then what is reserved, with their preparation
 * (SCRUM-85 AC2, ADR-0095), each in the backend's order.
 */
export function EquipmentOnRecord({ lines, reservations }: EquipmentOnRecordProps) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-ink-muted mb-3 text-sm font-semibold">Requested</h3>
        <RequestedEquipment lines={lines} />
      </div>
      <div>
        <h3 className="text-ink-muted mb-3 text-sm font-semibold">Reserved</h3>
        <ReservedEquipment reservations={reservations} />
      </div>
    </div>
  )
}
