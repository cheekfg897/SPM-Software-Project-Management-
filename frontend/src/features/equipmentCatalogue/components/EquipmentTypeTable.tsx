import { Link } from 'react-router'

import { DataTable } from '@/components/ui'
import type { DataTableColumn } from '@/components/ui'
import { equipmentTypePath } from '@/config/routes'

import type { EquipmentType } from '../api'
import { locationText } from '../locationText'

import { DescriptionText } from './DescriptionText'

const COLUMNS: DataTableColumn<EquipmentType>[] = [
  {
    header: 'Equipment',
    cell: (type) => (
      <Link to={equipmentTypePath(type.id)} className="text-ink hover:text-flare font-medium">
        {type.name}
      </Link>
    ),
  },
  { header: 'Description', cell: (type) => <DescriptionText description={type.description} /> },
  { header: 'Total held', cell: (type) => type.total_quantity },
  { header: 'Kept at', cell: (type) => locationText(type) },
]

/** Every equipment type, one row each, in the order the backend sent them (SCRUM-27 AC2). */
export function EquipmentTypeTable({ types }: { types: EquipmentType[] }) {
  return (
    <DataTable
      caption="Equipment types"
      columns={COLUMNS}
      rows={types}
      getRowKey={(type) => type.id}
    />
  )
}
