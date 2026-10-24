import { PreparationSummary } from '@/components/preparation/PreparationSummary'
import { EmptyState } from '@/components/ui'
import { STATUS_LABELS } from '@/features/booking/constants'
import { formatShortDate, formatTimeRange } from '@/lib/formatDate'

import type { StaffVenueArrangement } from '../api'

const NONE_ARRANGED = 'No venue is arranged for this event yet.'

/**
 * The event's venue arrangements, earliest first as the backend sends them: each venue, when,
 * where its request stands, and Venue Staff's preparation (SCRUM-84 AC2, ADR-0095).
 */
export function VenueArrangementList({ arrangements }: { arrangements: StaffVenueArrangement[] }) {
  if (arrangements.length === 0) {
    return <EmptyState message={NONE_ARRANGED} />
  }
  return (
    <ul className="space-y-3">
      {arrangements.map((arrangement) => (
        <li
          key={`${arrangement.venue_name}-${arrangement.starts_at}`}
          className="border-line/60 bg-surface/50 rounded-2xl border p-5"
        >
          <p className="text-ink font-medium">{arrangement.venue_name}</p>
          <p className="text-ink-muted text-sm">
            {formatShortDate(arrangement.starts_at)},{' '}
            {formatTimeRange(arrangement.starts_at, arrangement.ends_at)} ·{' '}
            {STATUS_LABELS[arrangement.status]}
          </p>
          <PreparationSummary preparation={arrangement} />
        </li>
      ))}
    </ul>
  )
}
