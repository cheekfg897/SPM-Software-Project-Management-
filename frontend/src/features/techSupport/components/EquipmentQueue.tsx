import { useId } from 'react'

import { ErrorAlert, Spinner } from '@/components/ui'
import { ROLE } from '@/config/roles'
import { selectSessionUser, useAppSelector } from '@/store'

import type { EquipmentType } from '../api'
import { useEquipmentAwaitingAction, useEquipmentTypes } from '../hooks'

import { EquipmentQueueRow } from './EquipmentQueueRow'

const TITLE = 'Equipment awaiting action'
/** The web app's own words: the backend sends no message with an empty queue (ADR-0051). */
const NOTHING_AWAITING = 'No equipment requests are awaiting action.'

function namesById(types: EquipmentType[]): Map<number, string> {
  const names = new Map<number, string>()
  for (const type of types) {
    names.set(type.id, type.name)
  }
  return names
}

/** The queue in the backend's order, its lines named from the catalogue, once both are read. */
function QueueContent() {
  const queue = useEquipmentAwaitingAction()
  const types = useEquipmentTypes()

  if (queue.isPending || types.isPending) {
    return (
      <p className="text-ink-muted mt-6 flex items-center gap-2">
        <Spinner /> Loading the equipment awaiting action…
      </p>
    )
  }
  if (queue.isError || types.isError) {
    return (
      <div className="mt-6">
        <ErrorAlert error={queue.error ?? types.error} />
      </div>
    )
  }

  const rows = queue.data.equipment_requests
  if (rows.length === 0) {
    return (
      <p className="border-line text-ink-muted mt-6 rounded-2xl border border-dashed px-6 py-12 text-center">
        {NOTHING_AWAITING}
      </p>
    )
  }
  const typeNames = namesById(types.data)
  return (
    <ul
      aria-label={TITLE}
      className="border-line/50 bg-surface/40 mt-6 space-y-1 rounded-3xl border p-2"
    >
      {rows.map((item) => (
        <li key={item.event.reference}>
          <EquipmentQueueRow item={item} typeNames={typeNames} />
        </li>
      ))}
    </ul>
  )
}

function QueueSection() {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="mt-12">
      <h2 id={headingId} className="font-display text-2xl font-semibold tracking-tight">
        {TITLE}
      </h2>
      <QueueContent />
    </section>
  )
}

/**
 * On Staff home, Technical Support's queue: every upcoming event's equipment still awaiting
 * them, soonest first, each opening the event's Equipment page (SCRUM-38, ADR-0022, ADR-0051).
 * Other roles see nothing, and nothing is asked for.
 */
export function EquipmentQueue() {
  const viewer = useAppSelector(selectSessionUser)
  if (viewer?.role !== ROLE.TECHNICAL_SUPPORT_STAFF) {
    return null
  }
  return <QueueSection />
}
