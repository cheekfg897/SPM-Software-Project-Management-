import type { ReactNode } from 'react'

import { SegmentedControl, TextAreaField, TextField } from '@/components/ui'
import type { SegmentedOption } from '@/components/ui'
import type { FieldErrors } from '@/lib/api'

type YesOrNo = 'yes' | 'no'

const REGISTRATION_QUESTION = 'Do attendees need to register?'
const REGISTRATION_OPTIONS: readonly SegmentedOption<YesOrNo>[] = [
  { value: 'yes', label: 'Yes' },
  { value: 'no', label: 'No' },
]

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-5">
      <h2 className="font-display text-ink text-lg font-semibold">{title}</h2>
      {children}
    </section>
  )
}

interface EventRequestFieldsProps {
  /** The backend's messages, keyed by field (`fieldErrorsOf(error)`). */
  fieldErrors: FieldErrors
  registrationRequired: boolean
  onRegistrationChange: (required: boolean) => void
}

/**
 * Everything an organiser says about their event (SCRUM-19 AC1), each field named as the API
 * names it and showing the backend's messages for it. Which fields a submission needs, and
 * every rule about them, is the backend's to say.
 */
export function EventRequestFields({
  fieldErrors,
  registrationRequired,
  onRegistrationChange,
}: EventRequestFieldsProps) {
  return (
    <div className="space-y-10">
      <Section title="About the event">
        <TextField label="Event name" name="name" required errors={fieldErrors.name} />
        <TextAreaField label="Purpose" name="purpose" errors={fieldErrors.purpose} />
        <TextAreaField label="Description" name="description" errors={fieldErrors.description} />
      </Section>

      <Section title="When">
        <div className="grid gap-5 sm:grid-cols-3">
          <TextField
            label="Date"
            name="proposed_date"
            type="date"
            errors={fieldErrors.proposed_date}
          />
          <TextField label="Starts" name="start_time" type="time" errors={fieldErrors.start_time} />
          <TextField label="Ends" name="end_time" type="time" errors={fieldErrors.end_time} />
        </div>
        <TextField
          label="Ends on a later day"
          name="end_date"
          type="date"
          hint="Only for an event that runs past midnight. Leave it empty if it ends the same day."
          errors={fieldErrors.end_date}
        />
      </Section>

      <Section title="Who and what">
        <TextField
          label="Expected attendance"
          name="expected_attendance"
          type="number"
          inputMode="numeric"
          min={1}
          step={1}
          errors={fieldErrors.expected_attendance}
        />
        <TextAreaField
          label="Venue requirements"
          name="venue_requirements"
          errors={fieldErrors.venue_requirements}
        />
        <TextAreaField
          label="Accessibility needs"
          name="accessibility_needs"
          errors={fieldErrors.accessibility_needs}
        />
        <TextAreaField
          label="Equipment requirements"
          name="equipment_requirements"
          errors={fieldErrors.equipment_requirements}
        />
        <div>
          <p className="text-ink mb-1.5 text-sm font-medium">{REGISTRATION_QUESTION}</p>
          <SegmentedControl
            label={REGISTRATION_QUESTION}
            options={REGISTRATION_OPTIONS}
            value={registrationRequired ? 'yes' : 'no'}
            onChange={(answer) => onRegistrationChange(answer === 'yes')}
          />
          <p className="text-ink-faint mt-1.5 text-sm">
            Your coordinator uses this when they open registration for the event.
          </p>
        </div>
      </Section>
    </div>
  )
}
