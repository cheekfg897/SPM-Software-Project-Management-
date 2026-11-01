import { TextAreaField, TextField } from '@/components/ui'
import type { FieldErrors } from '@/lib/api'

import type { EventRecord } from '../api'
import { openingValue } from '../eventEdit'

/**
 * When the event is, how many are expected and what it needs, each opened with what `record`
 * holds and showing the backend's messages for it: the coordinator's edit (SCRUM-33) and the
 * organiser's change request (SCRUM-56) ask for these the same way.
 */
export function TimingAndNeedsFields({
  record,
  errors,
}: {
  record: EventRecord
  errors: FieldErrors
}) {
  return (
    <>
      <div className="grid gap-5 sm:grid-cols-2">
        <TextField
          label="Date"
          name="proposed_date"
          type="date"
          defaultValue={openingValue(record, 'proposed_date')}
          errors={errors.proposed_date}
        />
        <TextField
          label="End date"
          name="end_date"
          type="date"
          hint="Moves with the date unless you change it too."
          defaultValue={openingValue(record, 'end_date')}
          errors={errors.end_date}
        />
        <TextField
          label="Starts"
          name="start_time"
          type="time"
          defaultValue={openingValue(record, 'start_time')}
          errors={errors.start_time}
        />
        <TextField
          label="Ends"
          name="end_time"
          type="time"
          defaultValue={openingValue(record, 'end_time')}
          errors={errors.end_time}
        />
      </div>
      <TextField
        label="Expected attendance"
        name="expected_attendance"
        type="number"
        inputMode="numeric"
        min={1}
        step={1}
        defaultValue={openingValue(record, 'expected_attendance')}
        errors={errors.expected_attendance}
      />
      <TextAreaField
        label="Venue requirements"
        name="venue_requirements"
        defaultValue={openingValue(record, 'venue_requirements')}
        errors={errors.venue_requirements}
      />
      <TextAreaField
        label="Equipment requirements"
        name="equipment_requirements"
        defaultValue={openingValue(record, 'equipment_requirements')}
        errors={errors.equipment_requirements}
      />
    </>
  )
}
