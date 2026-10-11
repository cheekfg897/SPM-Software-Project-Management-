import { DataTable } from '@/components/ui'
import type { DataTableColumn } from '@/components/ui'
import { selectSessionUser, useAppSelector } from '@/store'

import type { EquipmentAvailability } from '../api'
import { EQUIPMENT_RESERVER_ROLES } from '../constants'

import { ReserveForm } from './ReserveForm'

interface AvailabilityTableProps {
  reference: string
  rows: EquipmentAvailability[]
}

/** The shortfall in words, so it does not depend on colour to be seen. */
function shortfallText(row: EquipmentAvailability): string {
  return row.shortfall > 0 ? `Short by ${row.shortfall}` : 'None'
}

const READ_COLUMNS: DataTableColumn<EquipmentAvailability>[] = [
  { header: 'Equipment', cell: (row) => row.equipment_type_name },
  { header: 'Available', cell: (row) => row.available },
  { header: 'Requested', cell: (row) => row.requested },
  {
    header: 'Shortfall',
    cell: (row) => (
      <span className={row.shortfall > 0 ? 'text-danger font-semibold' : ''}>
        {shortfallText(row)}
      </span>
    ),
  },
]

/** What is free of each equipment type for the event's period, with a reserve control per type for Technical Support. */
export function AvailabilityTable({ reference, rows }: AvailabilityTableProps) {
  const user = useAppSelector(selectSessionUser)
  const canReserve = user !== null && EQUIPMENT_RESERVER_ROLES.includes(user.role)
  const columns = canReserve
    ? [
        ...READ_COLUMNS,
        {
          header: 'Reserve',
          cell: (row: EquipmentAvailability) => (
            <ReserveForm reference={reference} equipmentType={row} />
          ),
        },
      ]
    : READ_COLUMNS

  return (
    <DataTable
      caption="Equipment availability"
      columns={columns}
      rows={rows}
      getRowKey={(row) => row.equipment_type_id}
    />
  )
}
