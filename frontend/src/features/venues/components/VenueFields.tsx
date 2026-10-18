import { useId } from 'react'

import { TextAreaField, TextField } from '@/components/ui'
import { VENUE_LAYOUTS } from '@/config/venueLayouts'
import type { FieldErrors } from '@/lib/api'

import type { OpeningPeriod, Venue } from '../api'
import { WEEKDAYS } from '../constants'
import { listFieldErrors } from '../venueForm'

import { OpeningHoursFields } from './OpeningHoursFields'
import { VenueSection } from './VenueSection'

/**
 * What a new venue's form starts with: open every day 09:00 to 18:00, the hours the backend
 * gives a venue sent without any. Sending them keeps "no periods" meaning closed (ADR-0067).
 */
const STANDARD_HOURS: OpeningPeriod[] = WEEKDAYS.map(({ value }) => ({
  open: { day: value, time: '09:00' },
  close: { day: value, time: '18:00' },
}))

const LIST_HINT = 'One per line.'

/** The layouts as checkboxes, the venue's own ticked, with the backend's messages under them. */
function LayoutChoices({ chosen, errors }: { chosen: readonly string[]; errors: string[] }) {
  const errorsId = useId()
  const hasErrors = errors.length > 0

  return (
    <fieldset aria-describedby={hasErrors ? errorsId : undefined}>
      <legend className="text-ink mb-1.5 text-sm font-medium">Layouts it supports</legend>
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        {VENUE_LAYOUTS.map((layout) => (
          <label key={layout.value} className="text-ink flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="supported_layouts"
              value={layout.value}
              defaultChecked={chosen.includes(layout.value)}
              aria-invalid={hasErrors}
              className="accent-flare size-4"
            />
            {layout.label}
          </label>
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

interface VenueFieldsProps {
  /** The backend's messages, keyed by field (`fieldErrorsOf(error)`). */
  fieldErrors: FieldErrors
  /** The venue being changed; undefined for a new one. */
  initial: Venue | undefined
}

/**
 * Everything Venue Staff record about a venue (SCRUM-25 AC1, SCRUM-67 AC1), each field named as
 * the API names it and showing the backend's messages for it. Every rule is the backend's.
 */
export function VenueFields({ fieldErrors, initial }: VenueFieldsProps) {
  // A new venue left without them takes the standard times; a venue being changed keeps its own.
  const bufferHint = initial === undefined ? { hint: 'Leave empty for the standard time.' } : {}

  return (
    <>
      <VenueSection title="About the venue">
        <div className="space-y-5">
          <TextField
            label="Name"
            name="name"
            defaultValue={initial?.name}
            errors={fieldErrors.name}
          />
          <TextField
            label="Location"
            name="location"
            defaultValue={initial?.location}
            errors={fieldErrors.location}
          />
          <TextField
            label="Capacity"
            name="capacity"
            type="number"
            inputMode="numeric"
            defaultValue={initial?.capacity}
            errors={fieldErrors.capacity}
          />
        </div>
      </VenueSection>

      <VenueSection title="What it offers">
        <div className="space-y-5">
          <LayoutChoices
            chosen={initial?.supported_layouts ?? []}
            errors={listFieldErrors(fieldErrors, 'supported_layouts')}
          />
          <TextAreaField
            label="Facilities"
            name="facilities"
            hint={LIST_HINT}
            defaultValue={initial?.facilities.join('\n')}
            errors={listFieldErrors(fieldErrors, 'facilities')}
          />
          <TextAreaField
            label="Accessibility features"
            name="accessibility_features"
            hint={LIST_HINT}
            defaultValue={initial?.accessibility_features.join('\n')}
            errors={listFieldErrors(fieldErrors, 'accessibility_features')}
          />
        </div>
      </VenueSection>

      <VenueSection
        title="Setup and turnaround"
        description="How long each booking holds the venue before its event starts and after it ends."
      >
        <div className="grid gap-5 sm:grid-cols-2">
          <TextField
            label="Setup time (minutes)"
            name="setup_minutes"
            type="number"
            inputMode="numeric"
            {...bufferHint}
            defaultValue={initial?.setup_minutes}
            errors={fieldErrors.setup_minutes}
          />
          <TextField
            label="Turnaround time (minutes)"
            name="turnaround_minutes"
            type="number"
            inputMode="numeric"
            {...bufferHint}
            defaultValue={initial?.turnaround_minutes}
            errors={fieldErrors.turnaround_minutes}
          />
        </div>
      </VenueSection>

      <VenueSection title="Opening hours">
        <OpeningHoursFields
          initial={initial?.opening_hours ?? STANDARD_HOURS}
          fieldErrors={fieldErrors}
        />
      </VenueSection>
    </>
  )
}
