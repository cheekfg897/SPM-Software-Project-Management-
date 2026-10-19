import { Button, DataTable, ErrorAlert } from '@/components/ui'
import type { DataTableColumn } from '@/components/ui'
import { attributed } from '@/lib/attributed'

import type { EquipmentType, OutOfServiceEntry, OutOfServiceReason } from '../api'
import { OUT_OF_SERVICE_REASON_LABELS } from '../constants'
import { useReturnToService } from '../hooks'

/** e.g. "2 Damaged units", "1 Under maintenance unit". */
function unitsText(entry: OutOfServiceEntry): string {
  const units = entry.quantity === 1 ? 'unit' : 'units'
  return `${entry.quantity} ${OUT_OF_SERVICE_REASON_LABELS[entry.reason]} ${units}`
}

/** How many units are out for this reason: the entries the backend listed, added up. */
function unitsOutFor(entries: OutOfServiceEntry[], reason: OutOfServiceReason): number {
  let total = 0
  for (const entry of entries) {
    if (entry.reason === reason) {
      total += entry.quantity
    }
  }
  return total
}

function Count({ term, value }: { term: string; value: string | number }) {
  return (
    <div className="border-line/70 bg-surface/70 rounded-2xl border px-5 py-4">
      <dt className="text-ink-muted text-sm font-medium">{term}</dt>
      <dd className="text-ink mt-1 text-2xl font-semibold">{value}</dd>
    </div>
  )
}

interface OutOfServiceListProps {
  type: EquipmentType
  /** The type's units still out of service, as the backend listed them. */
  entries: OutOfServiceEntry[]
}

/**
 * How many of the type's units are in service and out of it (SCRUM-47 AC2), each batch still out
 * with who recorded it and when (AC4), and a way to put a batch back in service (AC1).
 */
export function OutOfServiceList({ type, entries }: OutOfServiceListProps) {
  const putBack = useReturnToService(String(type.id))
  const damaged = unitsOutFor(entries, 'damaged')
  const underMaintenance = unitsOutFor(entries, 'under_maintenance')
  const inService = type.total_quantity - damaged - underMaintenance

  const columns: DataTableColumn<OutOfServiceEntry>[] = [
    { header: 'Quantity', cell: (entry) => entry.quantity },
    { header: 'Reason', cell: (entry) => OUT_OF_SERVICE_REASON_LABELS[entry.reason] },
    {
      header: 'Recorded',
      cell: (entry) => attributed('Recorded', entry.recorded_by, entry.recorded_at),
    },
    {
      header: 'Put back',
      cell: (entry) => (
        <Button
          variant="secondary"
          isPending={putBack.isPending}
          onClick={() => putBack.mutate(entry.id)}
          aria-label={`Put ${unitsText(entry)} back in service`}
        >
          Back in service
        </Button>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div role="group" aria-label="Units in and out of service">
        <dl className="grid max-w-2xl gap-3 sm:grid-cols-3">
          <Count term="In service" value={`${inService} of ${type.total_quantity}`} />
          <Count term="Damaged" value={damaged} />
          <Count term="Under maintenance" value={underMaintenance} />
        </dl>
      </div>
      <ErrorAlert error={putBack.error} />
      {putBack.data !== undefined && (
        <p role="status" className="text-success text-sm">
          {unitsText(putBack.data)} {putBack.data.quantity === 1 ? 'is' : 'are'} back in service.{' '}
          {attributed('Put back', putBack.data.resolved_by, putBack.data.resolved_at)}.
        </p>
      )}
      {entries.length === 0 ? (
        <p className="text-ink-muted">Every unit is in service.</p>
      ) : (
        <DataTable
          caption="Units out of service"
          columns={columns}
          rows={entries}
          getRowKey={(entry) => entry.id}
        />
      )}
    </div>
  )
}
