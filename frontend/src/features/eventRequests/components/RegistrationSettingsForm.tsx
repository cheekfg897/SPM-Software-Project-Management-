import { useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { Button, ErrorAlert, SegmentedControl, TextField } from '@/components/ui'
import type { SegmentedOption } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'
import { toBusinessTimeIso } from '@/lib/businessTime'
import { formatDateTime } from '@/lib/formatDate'

import type { EventRecord, RegistrationChanges, RegistrationSettings } from '../api'
import { useUpdateRegistration } from '../hooks'
import { useFocusFirstError } from '../useFocusFirstError'

import { ActionCard } from './ActionCard'

type OpenOrClosed = 'open' | 'closed'

const REGISTRATION_LABEL = 'Registration'
const REGISTRATION_OPTIONS: readonly SegmentedOption<OpenOrClosed>[] = [
  { value: 'open', label: 'Open' },
  { value: 'closed', label: 'Closed' },
]
const CHOICE_HINT =
  'Pick one only to change it; left unpicked, registration stays as it is. Until a capacity ' +
  'is first saved, that follows what the organiser asked for.'
const CAPACITY_HINT = 'How many places attendees can take. Leave empty to keep the current number.'
const CUT_OFF_HINT =
  'In Singapore time, before the event starts. Leave empty to keep the current cut-off.'
const NO_CUT_OFF = 'No withdrawal cut-off: withdrawals close when the event starts.'

/** When withdrawals close, as the backend now holds it: at the cut-off, or at the start. */
function cutOffSentence(cutOff: string | null): string {
  if (cutOff === null) {
    return NO_CUT_OFF
  }
  return `Withdrawal cut-off: ${formatDateTime(cutOff)}.`
}

/** What the backend now holds, from its answer to the save (ADR-0075 decision 4, ADR-0115). */
function SavedSettings({ settings }: { settings: RegistrationSettings }) {
  const sentences = [
    settings.registration_enabled ? 'Registration is open.' : 'Registration is closed.',
  ]
  if (settings.registration_capacity !== null) {
    sentences.push(`Capacity: ${settings.registration_capacity}.`)
  }
  sentences.push(cutOffSentence(settings.withdrawal_cut_off))
  return (
    <p role="status" className="text-success text-sm">
      {sentences.join(' ')}
    </p>
  )
}

/**
 * Open or close registration for a confirmed event, set its capacity, and record or remove its
 * withdrawal cut-off (SCRUM-69). The event's record doesn't carry the current settings, so the
 * form doesn't guess them: nothing is picked or ticked and the boxes are empty, and only what
 * the coordinator changes is sent. Left out, the backend keeps what the event has. Every rule
 * is the backend's, and its messages show under the box they are about (ADR-0043, ADR-0075,
 * ADR-0115).
 */
export function RegistrationSettingsForm({ record }: { record: EventRecord }) {
  const [choice, setChoice] = useState<OpenOrClosed | null>(null)
  const [capacity, setCapacity] = useState('')
  const [cutOff, setCutOff] = useState('')
  const [removesCutOff, setRemovesCutOff] = useState(false)
  const formRef = useRef<HTMLFormElement>(null)
  const update = useUpdateRegistration(record.reference)
  useFocusFirstError(formRef, update.error)
  const asked = record.registration_required ? 'asked for' : 'did not ask for'
  const hasChange = choice !== null || capacity !== '' || cutOff !== '' || removesCutOff

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const changes: RegistrationChanges = {}
    if (choice !== null) {
      changes.registration_enabled = choice === 'open'
    }
    if (capacity !== '') {
      changes.registration_capacity = Number(capacity)
    }
    if (removesCutOff) {
      changes.withdrawal_cut_off = null
    } else if (cutOff !== '') {
      changes.withdrawal_cut_off = toBusinessTimeIso(cutOff)
    }
    update.mutate(changes)
  }

  return (
    <ActionCard
      title="Registration settings"
      description={`The organiser ${asked} registration. Attendees can register only while it is open.`}
    >
      <form ref={formRef} onSubmit={handleSubmit} className="space-y-4">
        <ErrorAlert error={update.error} />
        <div>
          <p className="text-ink mb-1.5 text-sm font-medium">{REGISTRATION_LABEL}</p>
          <SegmentedControl
            label={REGISTRATION_LABEL}
            options={REGISTRATION_OPTIONS}
            value={choice ?? ''}
            onChange={setChoice}
          />
          <p className="text-ink-faint mt-1.5 text-sm">{CHOICE_HINT}</p>
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
        <div>
          <TextField
            label="Withdrawal cut-off"
            name="withdrawal_cut_off"
            type="datetime-local"
            value={cutOff}
            onChange={(event) => setCutOff(event.target.value)}
            disabled={removesCutOff}
            errors={fieldErrorsOf(update.error).withdrawal_cut_off}
            hint={CUT_OFF_HINT}
          />
          <label className="text-ink mt-2 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={removesCutOff}
              onChange={(event) => setRemovesCutOff(event.target.checked)}
              className="accent-flare size-4"
            />
            Remove the cut-off
          </label>
        </div>
        <Button type="submit" isPending={update.isPending} disabled={!hasChange}>
          Save registration
        </Button>
        {update.isSuccess && <SavedSettings settings={update.data} />}
      </form>
    </ActionCard>
  )
}
