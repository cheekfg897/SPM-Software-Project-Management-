import { useState } from 'react'
import type { FormEvent } from 'react'

import { Button, ErrorAlert, SegmentedControl, TextField } from '@/components/ui'
import type { SegmentedOption } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { EventRecord, RegistrationChanges, RegistrationSettings } from '../api'
import { useUpdateRegistration } from '../hooks'

import { ActionCard } from './ActionCard'

type OpenOrClosed = 'open' | 'closed'

const REGISTRATION_LABEL = 'Registration'
const REGISTRATION_OPTIONS: readonly SegmentedOption<OpenOrClosed>[] = [
  { value: 'open', label: 'Open' },
  { value: 'closed', label: 'Closed' },
]
const CAPACITY_HINT = 'How many places attendees can take. Leave empty to keep the current number.'

/** What the backend now holds, from its answer to the save (ADR-0075 decision 4). */
function SavedSettings({ settings }: { settings: RegistrationSettings }) {
  const { registration_enabled: isOpen, registration_capacity: capacity } = settings
  return (
    <p role="status" className="text-success text-sm">
      {isOpen ? 'Registration is open.' : 'Registration is closed.'}
      {capacity !== null && ` Capacity: ${capacity}.`}
    </p>
  )
}

/**
 * Open or close registration for a confirmed event and set its capacity (SCRUM-69). The event's
 * record doesn't carry the current settings, so the choice starts at what the organiser asked
 * for and the capacity box empty; an empty box keeps the capacity the event has. Every rule is
 * the backend's, and its messages show under the box (ADR-0043, ADR-0075).
 */
export function RegistrationSettingsForm({ record }: { record: EventRecord }) {
  const [isOpen, setIsOpen] = useState(record.registration_required)
  const [capacity, setCapacity] = useState('')
  const update = useUpdateRegistration(record.reference)
  const asked = record.registration_required ? 'asked for' : 'did not ask for'

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const changes: RegistrationChanges = { registration_enabled: isOpen }
    if (capacity !== '') {
      changes.registration_capacity = Number(capacity)
    }
    update.mutate(changes)
  }

  return (
    <ActionCard
      title="Registration settings"
      description={`The organiser ${asked} registration. Attendees can register only while it is open.`}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <ErrorAlert error={update.error} />
        <div>
          <p className="text-ink mb-1.5 text-sm font-medium">{REGISTRATION_LABEL}</p>
          <SegmentedControl
            label={REGISTRATION_LABEL}
            options={REGISTRATION_OPTIONS}
            value={isOpen ? 'open' : 'closed'}
            onChange={(choice) => setIsOpen(choice === 'open')}
          />
        </div>
        <TextField
          label="Capacity"
          name="registration_capacity"
          type="number"
          inputMode="numeric"
          value={capacity}
          onChange={(event) => setCapacity(event.target.value)}
          errors={fieldErrorsOf(update.error).registration_capacity}
          hint={CAPACITY_HINT}
        />
        <Button type="submit" isPending={update.isPending}>
          Save registration
        </Button>
        {update.isSuccess && <SavedSettings settings={update.data} />}
      </form>
    </ActionCard>
  )
}
