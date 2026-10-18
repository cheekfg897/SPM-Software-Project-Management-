import { DataTable, EmptyState, ErrorAlert, Spinner } from '@/components/ui'
import type { DataTableColumn } from '@/components/ui'
import { formatDateTime } from '@/lib/formatDate'

import type { Registrant, RegistrantList } from '../api'
import { humanise } from '../humanise'
import { useRegistrants } from '../hooks'

import { RecordSection } from './RecordSection'

const NOBODY_YET = 'No one has registered yet.'

/** Each registrant's name, email, registration date and status (SCRUM-55 AC3). */
const COLUMNS: DataTableColumn<Registrant>[] = [
  { header: 'Name', cell: (registrant) => registrant.name },
  { header: 'Email', cell: (registrant) => registrant.email },
  { header: 'Registered', cell: (registrant) => formatDateTime(registrant.registered_at) },
  { header: 'Status', cell: (registrant) => humanise(registrant.status) },
]

/**
 * e.g. "3 registered of 80 places · 77 left", or "3 registered · no capacity set yet" until the
 * coordinator sets one (SCRUM-55 AC4, SCRUM-69). Every number is the backend's.
 */
function countAgainstCapacity(list: RegistrantList): string {
  const registered = `${String(list.registered_count)} registered`
  if (list.capacity === null) {
    return `${registered} · no capacity set yet`
  }
  return `${registered} of ${String(list.capacity)} places · ${String(list.places_left)} left`
}

function RegistrantsContent({ reference }: { reference: string }) {
  const registrants = useRegistrants(reference)
  if (registrants.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-2">
        <Spinner /> Loading the registrants…
      </p>
    )
  }
  if (registrants.isError) {
    return <ErrorAlert error={registrants.error} />
  }
  const list = registrants.data
  return (
    <div className="space-y-4">
      <p className="text-flare text-sm font-medium">{countAgainstCapacity(list)}</p>
      {list.items.length === 0 ? (
        <EmptyState message={NOBODY_YET} />
      ) : (
        <DataTable
          caption="Registrants"
          columns={COLUMNS}
          rows={list.items}
          getRowKey={(registrant) => registrant.email}
        />
      )}
    </div>
  )
}

/**
 * Who has registered for the event, in the backend's order, counted against its capacity, for
 * its organisation's organisers and its coordinator (SCRUM-55; ADR-0076).
 */
export function RegistrantsSection({ reference }: { reference: string }) {
  return (
    <RecordSection title="Registrants">
      <RegistrantsContent reference={reference} />
    </RecordSection>
  )
}
