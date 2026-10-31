import { Link } from 'react-router'

import { Badge } from '@/components/ui'
import { eventEquipmentPath } from '@/config/routes'
import { formatSchedule } from '@/features/eventRequests/formatSchedule'

import type { EquipmentAwaitingAction } from '../api'

interface EquipmentQueueRowProps {
  item: EquipmentAwaitingAction
  /** Each equipment type's name, by its id, from the catalogue. */
  typeNames: ReadonlyMap<number, string>
}

/** The backend's whole days to the event, as words: "Today", "1 day left", "12 days left". */
function daysLeft(days: number): string {
  if (days === 0) {
    return 'Today'
  }
  if (days === 1) {
    return '1 day left'
  }
  return `${days} days left`
}

/** Said after a line whose reservation a change marked for reassessment (SCRUM-60 AC6). */
const TO_REASSESS = ' (reservation to reassess)'

/** The type's name from the catalogue, or its id when the catalogue doesn't list it yet. */
function typeName(typeNames: ReadonlyMap<number, string>, equipmentTypeId: number): string {
  return typeNames.get(equipmentTypeId) ?? `Equipment type ${equipmentTypeId}`
}

/**
 * e.g. "Projector × 2, Microphone × 4 (reservation to reassess)", then each type to reassess the
 * event has no line for, by name alone: "Lectern (reservation to reassess)" (ADR-0114 decision
 * 22). A type the catalogue doesn't list yet is named by its id, so its line still shows
 * (ADR-0061).
 */
function equipmentOf(
  item: EquipmentAwaitingAction,
  typeNames: ReadonlyMap<number, string>,
): string {
  const named: string[] = []
  const typesWithALine: number[] = []
  for (const line of item.equipment_lines) {
    const toReassess = item.equipment_type_ids_to_reassess.includes(line.equipment_type_id)
    named.push(
      `${typeName(typeNames, line.equipment_type_id)} × ${line.quantity}${toReassess ? TO_REASSESS : ''}`,
    )
    typesWithALine.push(line.equipment_type_id)
  }
  for (const equipmentTypeId of item.equipment_type_ids_to_reassess) {
    if (!typesWithALine.includes(equipmentTypeId)) {
      named.push(`${typeName(typeNames, equipmentTypeId)}${TO_REASSESS}`)
    }
  }
  return named.join(', ')
}

/**
 * One event in the queue: when it is, what it is, the equipment still to arrange and how long is
 * left. It opens the event's Equipment page (SCRUM-38 AC2, ADR-0061).
 */
export function EquipmentQueueRow({ item, typeNames }: EquipmentQueueRowProps) {
  const { event } = item
  return (
    <Link
      to={eventEquipmentPath(event.reference)}
      className="focus-visible:outline-flare block rounded-2xl focus-visible:outline-2"
    >
      <div className="hover:bg-surface-raised flex items-center gap-5 rounded-2xl p-4 transition">
        <div className="min-w-0 flex-1">
          <p className="text-flare text-sm font-medium">{formatSchedule(event)}</p>
          <h3 className="font-display text-ink mt-1 truncate text-lg font-semibold tracking-tight">
            {event.name}
          </h3>
          <p className="text-ink-muted mt-1 text-sm">
            {event.reference} · {equipmentOf(item, typeNames)}
          </p>
        </div>
        <Badge>{daysLeft(item.days_remaining)}</Badge>
      </div>
    </Link>
  )
}
