import { DataTable } from '@/components/ui'
import type { DataTableColumn } from '@/components/ui'
import { PREPARATION_STATUS_LABELS } from '@/config/preparation'
import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { formatShortDate, formatTimeRange } from '@/lib/formatDate'
import { selectSessionUser, useAppSelector } from '@/store'

import type { EquipmentReservation } from '../api'

import { ReservationPreparationForm } from './ReservationPreparationForm'

const NO_RESERVER_TEXT = 'Unknown'
const NO_NOTES_TEXT = 'None'
/** Only Technical Support Staff record preparation (SCRUM-85, ADR-0050); the coordinator reads it. */
const PREPARER_ROLES: readonly Role[] = [ROLE.TECHNICAL_SUPPORT_STAFF]

const READ_COLUMNS: DataTableColumn<EquipmentReservation>[] = [
  { header: 'Equipment', cell: (row) => row.equipment_type_name },
  { header: 'Quantity', cell: (row) => row.quantity },
  { header: 'Reserved by', cell: (row) => row.reserved_by ?? NO_RESERVER_TEXT },
  {
    header: 'When',
    cell: (row) =>
      `${formatShortDate(row.starts_at)}, ${formatTimeRange(row.starts_at, row.ends_at)}`,
  },
  { header: 'Preparation', cell: (row) => PREPARATION_STATUS_LABELS[row.preparation_status] },
  { header: 'Preparation notes', cell: (row) => row.preparation_notes ?? NO_NOTES_TEXT },
]

interface ReservationListProps {
  reference: string
  reservations: EquipmentReservation[]
}

/**
 * The equipment already reserved for the event, with each reservation's preparation (SCRUM-85
 * AC2), and for Technical Support a form in each row to record it (AC1, ADR-0081).
 */
export function ReservationList({ reference, reservations }: ReservationListProps) {
  const user = useAppSelector(selectSessionUser)
  const canPrepare = user !== null && PREPARER_ROLES.includes(user.role)

  if (reservations.length === 0) {
    return <p className="text-ink-muted">No equipment has been reserved for this event yet.</p>
  }
  const columns = canPrepare
    ? [
        ...READ_COLUMNS,
        {
          header: 'Record preparation',
          cell: (row: EquipmentReservation) => (
            <ReservationPreparationForm reference={reference} reservation={row} />
          ),
        },
      ]
    : READ_COLUMNS
  return (
    <DataTable
      caption="Reserved equipment"
      columns={columns}
      rows={reservations}
      getRowKey={(row) => row.id}
    />
  )
}
