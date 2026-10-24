import { DataTable } from '@/components/ui'
import type { DataTableColumn } from '@/components/ui'
import { EQUIPMENT_LINE_STATUS_LABELS } from '@/features/equipment/constants'

import type { OrganiserEquipmentLine } from '../api'

const COLUMNS: DataTableColumn<OrganiserEquipmentLine>[] = [
  { header: 'Equipment', cell: (line) => line.equipment_type_name },
  { header: 'Requested', cell: (line) => String(line.quantity) },
  { header: 'Status', cell: (line) => EQUIPMENT_LINE_STATUS_LABELS[line.status] },
  {
    header: 'Provided',
    cell: (line) =>
      line.provided_quantity === null ? 'Not reviewed yet' : String(line.provided_quantity),
  },
]

/**
 * What the organiser asked for and what they will get, line by line (SCRUM-37 AC5, SCRUM-48
 * AC5, ADR-0098): the equipment, the quantity asked for, the status and the quantity provided.
 * The backend leaves out what is internal, so the page hides nothing itself.
 */
export function OrganiserEquipment({ lines }: { lines: OrganiserEquipmentLine[] }) {
  return (
    <DataTable
      caption="Equipment requested"
      columns={COLUMNS}
      rows={lines}
      getRowKey={(line) => line.id}
    />
  )
}
