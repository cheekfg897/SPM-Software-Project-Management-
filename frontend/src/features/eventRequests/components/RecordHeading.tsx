import { StatusChip } from '@/components/ui'

import type { EventRequest } from '../api'
import { formatSchedule } from '../formatSchedule'

/** Under the event's name on every view of its record: when it runs, its status and reference. */
export function RecordHeading({ request }: { request: EventRequest }) {
  return (
    <>
      <p className="text-flare mt-3 font-medium">{formatSchedule(request)}</p>
      <div className="mt-3 flex items-center gap-3">
        <StatusChip status={request.status} />
        <span className="text-ink-muted text-sm">{request.reference}</span>
      </div>
    </>
  )
}
