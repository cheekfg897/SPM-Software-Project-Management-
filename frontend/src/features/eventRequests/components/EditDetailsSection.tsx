import { ButtonLink } from '@/components/ui'
import { editEventPath } from '@/config/routes'

import { RecordSection } from './RecordSection'

/** The assigned coordinator's way to the event's edit form (SCRUM-33 AC1, ADR-0079). */
export function EditDetailsSection({ reference }: { reference: string }) {
  return (
    <RecordSection title="Edit details">
      <p className="text-ink-muted text-sm">
        Change the notes, needs, timing or size as plans firm up. A change to the date, times,
        attendance or requirements is significant: the arrangements already made are reassessed.
      </p>
      <div className="mt-4">
        <ButtonLink to={editEventPath(reference)} variant="secondary">
          Edit event details
        </ButtonLink>
      </div>
    </RecordSection>
  )
}
