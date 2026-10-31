import { ButtonLink } from '@/components/ui'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { editEventPath } from '@/config/routes'

import type { EventRecord } from '../api'

import { RecordSection } from './RecordSection'

/**
 * The statuses the backend lets the coordinator's edit through: once they have approved the
 * request, until it is Confirmed (SCRUM-110 AC1, ADR-0116). Before approval, changes go through a
 * clarification or the organiser's change request; a Confirmed event changes only through a
 * change request (SCRUM-33 AC8).
 */
const EDITABLE_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
]

/**
 * The assigned coordinator's way to the event's edit form (SCRUM-33 AC1, ADR-0079), offered only
 * in the statuses the backend accepts an edit in (ADR-0101, ADR-0116). Whether it goes ahead is
 * still the backend's call, and the form shows its refusal.
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
