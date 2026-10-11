import { DataTable } from '@/components/ui'
import type { DataTableColumn } from '@/components/ui'
import { formatShortDate, formatTimeRange } from '@/lib/formatDate'

import type { EquipmentReservation } from '../api'

const NO_RESERVER_TEXT = 'Unknown'

const COLUMNS: DataTableColumn<EquipmentReservation>[] = [
  { header: 'Equipment', cell: (row) => row.equipment_type_name },
  { header: 'Quantity', cell: (row) => row.quantity },
  { header: 'Reserved by', cell: (row) => row.reserved_by ?? NO_RESERVER_TEXT },
  {
    header: 'When',
    cell: (row) =>
      `${formatShortDate(row.starts_at)}, ${formatTimeRange(row.starts_at, row.ends_at)}`,
  },
]

interface ReservationListProps {
  reservations: EquipmentReservation[]
}

/** The equipment already reserved for the event. */
export function ReservationList({ reservations }: ReservationListProps) {
  if (reservations.length === 0) {
    return <p className="text-ink-muted">No equipment has been reserved for this event yet.</p>
  }
  return (
    <DataTable
      caption="Reserved equipment"
      columns={COLUMNS}
      rows={reservations}
      getRowKey={(row) => row.id}
    />
  )
}
