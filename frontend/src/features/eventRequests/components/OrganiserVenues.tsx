import { DataTable } from '@/components/ui'
import type { DataTableColumn } from '@/components/ui'
import { LAYOUT_OPTIONS } from '@/config/roomLayouts'
import { formatShortDate, formatTimeRange } from '@/lib/formatDate'

import type { OrganiserVenueArrangement } from '../api'

/** The layout in words, or that none was asked for, as a booking request's details say it. */
function layoutLabel(layout: string | null): string {
  const option = LAYOUT_OPTIONS.find((candidate) => candidate.value === layout)
  return option?.label ?? 'No layout set'
}

const COLUMNS: DataTableColumn<OrganiserVenueArrangement>[] = [
  {
    header: 'Venue',
    cell: (arrangement) => (
      <>
        <span className="text-ink block">{arrangement.venue_name}</span>
        <span className="text-ink-muted block">{arrangement.venue_location}</span>
      </>
    ),
  },
  {
    header: 'When',
    cell: (arrangement) =>
      `${formatShortDate(arrangement.starts_at)}, ${formatTimeRange(arrangement.starts_at, arrangement.ends_at)}`,
  },
  { header: 'Purpose', cell: (arrangement) => arrangement.purpose },
  { header: 'Layout', cell: (arrangement) => layoutLabel(arrangement.layout) },
  { header: 'Expected occupancy', cell: (arrangement) => String(arrangement.expected_occupancy) },
]

/**
 * The confirmed event's venues, as its organiser sees them (SCRUM-49 AC11, ADR-0099): each venue
 * and where it is, when it is booked, and what was arranged. The backend sends them only once the
 * event is confirmed, and leaves out what is internal.
 */
export function OrganiserVenues({ arrangements }: { arrangements: OrganiserVenueArrangement[] }) {
  return (
    <DataTable
      caption="Venues booked"
      columns={COLUMNS}
      rows={arrangements}
      getRowKey={(arrangement) => `${arrangement.venue_name} ${arrangement.starts_at}`}
    />
  )
}
