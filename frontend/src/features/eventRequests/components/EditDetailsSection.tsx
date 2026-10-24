import { ButtonLink } from '@/components/ui'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { editEventPath } from '@/config/routes'

import type { EventRecord } from '../api'

import { RecordSection } from './RecordSection'

/**
 * The statuses the backend lets the coordinator's edit through: every status before Confirmed
 * (SCRUM-33 AC8, ADR-0101). A Confirmed event changes only through a change request.
 */
const EDITABLE_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.SUBMITTED,
  EVENT_REQUEST_STATUS.UNDER_REVIEW,
  EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
]

/**
 * The assigned coordinator's way to the event's edit form (SCRUM-33 AC1, ADR-0079), offered only
 * in the statuses the backend accepts an edit in (ADR-0101). Whether it goes ahead is still the
 * backend's call, and the form shows its refusal.
 */
export function EditDetailsSection({ record }: { record: EventRecord }) {
  if (!EDITABLE_STATUSES.includes(record.status)) {
    return null
  }
  return (
    <RecordSection title="Edit details">
      <p className="text-ink-muted text-sm">
        Change the notes, needs, timing or size as plans firm up. A change to the date, times,
        attendance or requirements is significant: the arrangements already made are reassessed.
      </p>
      <div className="mt-4">
        <ButtonLink to={editEventPath(record.reference)} variant="secondary">
          Edit event details
        </ButtonLink>
      </div>
    </RecordSection>
  )
}
