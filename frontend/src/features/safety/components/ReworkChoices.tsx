import { useId } from 'react'

import { formatShortDate, formatTimeRange } from '@/lib/formatDate'

import type { SafetyReviewEquipment, SafetyReviewVenue } from '../api'

/** What the Safety Officer has ticked to rework, by id, in the order ticked (SCRUM-99 AC2). */
export interface Rework {
  flagged_arrangement_ids: number[]
  reopened_line_ids: number[]
}

/** `ids` with `id` added, or taken out if it was there already. */
function toggled(ids: number[], id: number): number[] {
  if (ids.includes(id)) {
    return ids.filter((ticked) => ticked !== id)
  }
  return [...ids, id]
}

interface ChoiceProps {
  label: string
  checked: boolean
  invalid: boolean
  onToggle: () => void
}

function Choice({ label, checked, invalid, onToggle }: ChoiceProps) {
  return (
    <label className="text-ink flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        aria-invalid={invalid}
        className="accent-flare size-4"
      />
      {label}
    </label>
  )
}

interface ReworkChoicesProps {
  venues: SafetyReviewVenue[]
  equipment: SafetyReviewEquipment[]
  rework: Rework
  onChange: (rework: Rework) => void
  /** The backend's messages about what was named. */
  errors: string[]
}

/**
 * Each booked venue and equipment request as a checkbox, for the Safety Officer to name what
 * Venue Staff or Technical Support must look at again on a Reject or Request Changes (SCRUM-99
 * AC2). Whether naming is allowed with the outcome chosen is the backend's to say: its messages
 * show under the boxes.
 */
export function ReworkChoices({ venues, equipment, rework, onChange, errors }: ReworkChoicesProps) {
  const errorsId = useId()
  const hasErrors = errors.length > 0

  return (
    <fieldset aria-describedby={hasErrors ? errorsId : undefined}>
      <legend className="text-ink mb-1.5 text-sm font-semibold">What to rework</legend>
      <p className="text-ink-faint mb-2 text-sm">
        With Reject or Request changes, tick what Venue Staff or Technical Support must look at
        again.
      </p>
      <div className="space-y-2">
        {venues.map((venue) => (
          <Choice
            key={`venue-${String(venue.id)}`}
            label={`${venue.name}, ${formatShortDate(venue.starts_at)}, ${formatTimeRange(venue.starts_at, venue.ends_at)}`}
            checked={rework.flagged_arrangement_ids.includes(venue.id)}
            invalid={hasErrors}
            onToggle={() =>
              onChange({
                ...rework,
                flagged_arrangement_ids: toggled(rework.flagged_arrangement_ids, venue.id),
              })
            }
          />
        ))}
        {equipment.map((line) => (
          <Choice
            key={`line-${String(line.id)}`}
            label={`${line.equipment_type_name}, ${String(line.quantity)} requested`}
            checked={rework.reopened_line_ids.includes(line.id)}
            invalid={hasErrors}
            onToggle={() =>
              onChange({ ...rework, reopened_line_ids: toggled(rework.reopened_line_ids, line.id) })
            }
          />
        ))}
      </div>
      {hasErrors && (
        <ul id={errorsId} className="text-danger mt-1.5 space-y-0.5 text-sm">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
    </fieldset>
  )
}
