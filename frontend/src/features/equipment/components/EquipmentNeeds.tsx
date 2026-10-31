import { useState } from 'react'

import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { Button, DataTable } from '@/components/ui'
import type { DataTableColumn } from '@/components/ui'
import { selectSessionUser, useAppSelector } from '@/store'

import type { EquipmentLine, EquipmentLineStatus, EquipmentType, EventEquipmentLines } from '../api'
import { EQUIPMENT_LINE_STATUS_LABELS } from '../constants'
import { equipmentTypeName } from '../equipmentTypeName'
import { hasOutcome } from '../lineOutcome'

import { AddLineForm } from './AddLineForm'
import { ChangeLineForm } from './ChangeLineForm'
import { OutcomeForm } from './OutcomeForm'
import { OutcomeSummary } from './OutcomeSummary'
import { RemoveLineConfirm } from './RemoveLineConfirm'

/**
 * Only coordinators record equipment (SCRUM-37, ADR-0019). The backend shows a coordinator only
 * the lines of an event assigned to them, so one who sees the lines is that event's (ADR-0065).
 */
const EQUIPMENT_LINE_EDITOR_ROLES: readonly Role[] = [ROLE.EVENT_COORDINATOR]
/** Only Technical Support record a line's outcome, on any event (SCRUM-48, ADR-0040). */
const EQUIPMENT_OUTCOME_RECORDER_ROLES: readonly Role[] = [ROLE.TECHNICAL_SUPPORT_STAFF]
/**
 * The statuses the backend lets the coordinator change the lines in: once the request is
 * approved, until the event is confirmed (EQUIPMENT_EDITABLE_STATUSES, SCRUM-110 AC3, ADR-0116).
 */
const LINES_EDITABLE_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
]

/** Each status's colour, beside its words (ADR-0065). */
const STATUS_TONES: Record<EquipmentLineStatus, string> = {
  requested: 'text-flare',
  fulfilled: 'text-success',
  partially_fulfilled: 'text-ember',
  unavailable: 'text-danger',
}

/** The line a coordinator is changing or about to remove, or Technical Support are reviewing. */
interface LineSelection {
  line: EquipmentLine
  action: 'change' | 'remove' | 'outcome'
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
      cell: (line) => (
        <span className={`font-medium ${STATUS_TONES[line.status]}`}>
          {EQUIPMENT_LINE_STATUS_LABELS[line.status]}
        </span>
      ),
    },
    { header: 'Outcome', cell: (line) => <OutcomeSummary line={line} /> },
  ]
}

interface EquipmentNeedsProps {
  reference: string
  needs: EventEquipmentLines
  equipmentTypes: EquipmentType[]
}

/**
 * What the event needs (SCRUM-37): its equipment lines in the order the backend sent them, each
 * with Technical Support's outcome (SCRUM-48). Its coordinator gets the controls to add, change
 * and remove lines while the event's status allows it (SCRUM-110), and is told when it does
 * otherwise; Technical Support record or revise each outcome, one at a time, in any status.
 */
export function EquipmentNeeds({ reference, needs, equipmentTypes }: EquipmentNeedsProps) {
  const user = useAppSelector(selectSessionUser)
  const isLineEditor = user !== null && EQUIPMENT_LINE_EDITOR_ROLES.includes(user.role)
  const canEdit = isLineEditor && LINES_EDITABLE_STATUSES.includes(needs.event.status)
  const canRecordOutcome = user !== null && EQUIPMENT_OUTCOME_RECORDER_ROLES.includes(user.role)
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
  const reviewColumn: DataTableColumn<EquipmentLine> = {
    header: 'Review',
    cell: (line) => {
      const verb = hasOutcome(line) ? 'Revise' : 'Record'
      return (
        <Button
          variant="secondary"
          aria-label={`${verb} outcome for ${nameOf(line)}`}
          onClick={() => setSelection({ line, action: 'outcome' })}
        >
          {verb} outcome
        </Button>
      )
    },
  }
  const columns = readColumns(equipmentTypes)
  if (canEdit) {
    columns.push(actionsColumn)
  }
  if (canRecordOutcome) {
    columns.push(reviewColumn)
  }

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
      {isLineEditor && !canEdit && (
        <p className="text-ink-muted">
          Equipment can be added, changed or removed once the request is approved, until the event
          is confirmed.
        </p>
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
      {selection?.action === 'outcome' && (
        <OutcomeForm
          key={selection.line.id}
          reference={reference}
          line={selection.line}
          lineName={nameOf(selection.line)}
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
