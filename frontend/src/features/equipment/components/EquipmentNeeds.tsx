import { useState } from 'react'

import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { Button, DataTable } from '@/components/ui'
import type { DataTableColumn } from '@/components/ui'
import { selectSessionUser, useAppSelector } from '@/store'

import type { EquipmentLine, EquipmentLineStatus, EquipmentType, EventEquipmentLines } from '../api'
import { equipmentTypeName } from '../equipmentTypeName'

import { AddLineForm } from './AddLineForm'
import { ChangeLineForm } from './ChangeLineForm'
import { RemoveLineConfirm } from './RemoveLineConfirm'

/**
 * Only coordinators record equipment (SCRUM-37, ADR-0019). The backend shows a coordinator only
 * the lines of an event assigned to them, so one who sees the lines is that event's (ADR-0050).
 */
const EQUIPMENT_LINE_EDITOR_ROLES: readonly Role[] = [ROLE.EVENT_COORDINATOR]

/** Each status in words, so it does not depend on colour to be read (ADR-0050). */
const STATUS_TEXT: Record<EquipmentLineStatus, { label: string; tone: string }> = {
  requested: { label: 'Awaiting Technical Support', tone: 'text-flare' },
  fulfilled: { label: 'Fulfilled', tone: 'text-success' },
  partially_fulfilled: { label: 'Partly fulfilled', tone: 'text-ember' },
  unavailable: { label: 'Unavailable', tone: 'text-danger' },
}

/** The line a coordinator is changing or about to remove. */
interface LineSelection {
  line: EquipmentLine
  action: 'change' | 'remove'
}

function readColumns(equipmentTypes: EquipmentType[]): DataTableColumn<EquipmentLine>[] {
  return [
    {
      header: 'Equipment',
      cell: (line) => equipmentTypeName(equipmentTypes, line.equipment_type_id),
    },
    { header: 'Quantity', cell: (line) => line.quantity },
    {
      header: 'Technical notes',
      cell: (line) => line.notes ?? <span className="text-ink-faint">No notes</span>,
    },
    {
      header: 'Status',
      cell: (line) => {
        const { label, tone } = STATUS_TEXT[line.status]
        return <span className={`font-medium ${tone}`}>{label}</span>
      },
    },
  ]
}

interface EquipmentNeedsProps {
  reference: string
  needs: EventEquipmentLines
  equipmentTypes: EquipmentType[]
}

/**
 * What the event needs (SCRUM-37): its equipment lines in the order the backend sent them, and
 * for its coordinator the controls to add, change and remove them, one at a time.
 */
export function EquipmentNeeds({ reference, needs, equipmentTypes }: EquipmentNeedsProps) {
  const user = useAppSelector(selectSessionUser)
  const canEdit = user !== null && EQUIPMENT_LINE_EDITOR_ROLES.includes(user.role)
  const [selection, setSelection] = useState<LineSelection | null>(null)
  const lines = needs.equipment_lines

  function nameOf(line: EquipmentLine): string {
    return equipmentTypeName(equipmentTypes, line.equipment_type_id)
  }

  function closeSelection() {
    setSelection(null)
  }

  const actionsColumn: DataTableColumn<EquipmentLine> = {
    header: 'Change or remove',
    cell: (line) => (
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          aria-label={`Change ${nameOf(line)}`}
          onClick={() => setSelection({ line, action: 'change' })}
        >
          Change
        </Button>
        <Button
          variant="ghost"
          aria-label={`Remove ${nameOf(line)}`}
          onClick={() => setSelection({ line, action: 'remove' })}
        >
          Remove
        </Button>
      </div>
    ),
  }
  const shownColumns = readColumns(equipmentTypes)
  const columns = canEdit ? [...shownColumns, actionsColumn] : shownColumns

  return (
    <section aria-labelledby="needs-heading" className="space-y-4">
      <h2 id="needs-heading" className="text-xl font-semibold">
        What this event needs
      </h2>
      <p className="text-ink-muted">
        {needs.event.name}: one line for each type of equipment, with how many and any technical
        notes for Technical Support.
      </p>
      {lines.length === 0 ? (
        <p className="text-ink-muted">No equipment has been asked for yet.</p>
      ) : (
        <DataTable
          caption="Equipment lines"
          columns={columns}
          rows={lines}
          getRowKey={(line) => line.id}
        />
      )}
      {canEdit && selection === null && (
        <AddLineForm reference={reference} equipmentTypes={equipmentTypes} />
      )}
      {selection?.action === 'change' && (
        <ChangeLineForm
          key={selection.line.id}
          reference={reference}
          equipmentTypes={equipmentTypes}
          line={selection.line}
          onDone={closeSelection}
        />
      )}
      {selection?.action === 'remove' && (
        <RemoveLineConfirm
          key={selection.line.id}
          reference={reference}
          line={selection.line}
          lineName={nameOf(selection.line)}
          onDone={closeSelection}
        />
      )}
    </section>
  )
}
