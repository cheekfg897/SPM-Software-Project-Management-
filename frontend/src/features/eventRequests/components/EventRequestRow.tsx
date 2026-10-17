import { EventArt, StatusChip } from '@/components/ui'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'

import type { EventListRow, EventRequest } from '../api'
import { formatSchedule } from '../formatSchedule'

/** A row of any role's list: the list fields, and the attendance when the list carries it. */
type ListedRequest = EventListRow & Partial<Pick<EventRequest, 'expected_attendance'>>

/** A number from the reference, so a request keeps the same artwork every time it's shown. */
function artSeed(reference: string): number {
  let seed = 0
  for (const character of reference) {
    seed += character.charCodeAt(0)
  }
  return seed
}

/**
 * The second line: the reference, and the attendance once there is one. Technical Support's list
 * doesn't carry attendance at all (ADR-0051).
 */
function detailsOf(request: ListedRequest): string {
  const attendance = request.expected_attendance ?? null
  if (attendance === null) {
    return request.reference
  }
  return `${request.reference} · ${attendance} expected`
}

/**
 * One request in a role's list: when, what, its reference and its status. A draft has
 * a dashed outline and a faint date line, so it stands apart from submitted requests
 * (SCRUM-20 AC2).
 */
export function EventRequestRow({ request }: { request: ListedRequest }) {
  const isDraft = request.status === EVENT_REQUEST_STATUS.DRAFT
  const outline = isDraft ? 'border-dashed border-line' : 'border-transparent'
  const scheduleColour = isDraft ? 'text-ink-faint' : 'text-flare'

  return (
    <div
      className={`hover:bg-surface-raised flex items-center gap-5 rounded-2xl border p-4 transition ${outline}`}
    >
      <EventArt seed={artSeed(request.reference)} />
      <div className="min-w-0 flex-1">
        <p className={`text-sm font-medium ${scheduleColour}`}>{formatSchedule(request)}</p>
        <h2 className="font-display text-ink mt-1 truncate text-lg font-semibold tracking-tight">
          {request.name}
        </h2>
        <p className="text-ink-muted mt-1 text-sm">{detailsOf(request)}</p>
      </div>
      <StatusChip status={request.status} />
    </div>
  )
}
