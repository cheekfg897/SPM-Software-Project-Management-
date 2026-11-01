import { useRef } from 'react'
import type { FormEvent } from 'react'

import { Button, ButtonLink, ErrorAlert, TextAreaField } from '@/components/ui'
import { coordinatorEventPath } from '@/config/routes'
import { fieldErrorsOf } from '@/lib/api'

import type { EditedEventRequest, EventRecord } from '../api'
import { changedFields, openingValue } from '../eventEdit'
import { describeHistoryEntry } from '../eventHistory'
import { useEditEventRequest } from '../hooks'
import { useFocusFirstError } from '../useFocusFirstError'

import { DescribedEntryView } from './DescribedEntryView'
import { RecordSection } from './RecordSection'
import { TimingAndNeedsFields } from './TimingAndNeedsFields'

const SIGNIFICANT_HINT =
  'Changing these is a significant change: the arrangements already made are reassessed.'
const REASSESSMENT_NOTICE =
  'A significant change means the arrangements already made for this event will be reassessed.'
const NOTHING_CHANGED = 'Nothing changed: the event already held these details.'

/** What the save changed, each as the history words it, with the significant ones marked. */
function SavedChanges({ edited, reference }: { edited: EditedEventRequest; reference: string }) {
  const { changes } = edited
  const hasSignificant = changes.some((change) => change.significant)
  return (
    <RecordSection title="Saved">
      <div className="border-success/40 bg-success/10 space-y-4 rounded-2xl border p-5">
        {changes.length === 0 && <p className="text-ink">{NOTHING_CHANGED}</p>}
        <ul className="space-y-4">
          {changes.map((change) => (
            <li key={change.field}>
              <DescribedEntryView
                described={describeHistoryEntry({ kind: 'field_changed', details: { ...change } })}
              />
            </li>
          ))}
        </ul>
        {hasSignificant && <p className="text-ink-muted text-sm">{REASSESSMENT_NOTICE}</p>}
        <ButtonLink to={coordinatorEventPath(reference)} variant="secondary">
          Back to the event
        </ButtonLink>
      </div>
    </RecordSection>
  )
}

/**
 * The fields the assigned coordinator may change, opened with what the event holds (SCRUM-33
 * AC1). The name, purpose, registration and the venue and equipment arrangements aren't here:
 * they aren't the coordinator's to change on this form (AC3). Saving sends only what changed;
 * the backend checks it, and its messages show under the fields they are about.
 */
export function EditEventForm({ record }: { record: EventRecord }) {
  const edit = useEditEventRequest(record.reference)
  const formRef = useRef<HTMLFormElement>(null)
  useFocusFirstError(formRef, edit.error)
  const errors = fieldErrorsOf(edit.error)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    edit.mutate(changedFields(new FormData(event.currentTarget), record))
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="max-w-2xl">
      <ErrorAlert error={edit.error} />
      <RecordSection title="Notes and needs">
        <div className="space-y-5">
          <TextAreaField
            label="Description"
            name="description"
            defaultValue={openingValue(record, 'description')}
            errors={errors.description}
          />
          <TextAreaField
            label="Programme notes"
            name="programme_notes"
            hint="The organiser sees these on their event."
            defaultValue={openingValue(record, 'programme_notes')}
            errors={errors.programme_notes}
          />
          <TextAreaField
            label="Accessibility needs"
            name="accessibility_needs"
            defaultValue={openingValue(record, 'accessibility_needs')}
            errors={errors.accessibility_needs}
          />
          <TextAreaField
            label="Planning notes"
            name="internal_planning_notes"
            hint="Staff and the organiser see these. Your event page doesn't show the current notes, so this opens empty: what you type replaces them, and leaving it empty keeps them."
            errors={errors.internal_planning_notes}
          />
        </div>
      </RecordSection>
      <RecordSection title="When, how many and what it needs">
        <div className="space-y-5">
          <p className="text-ink-muted text-sm">{SIGNIFICANT_HINT}</p>
          <TimingAndNeedsFields record={record} errors={errors} />
        </div>
      </RecordSection>
      <div className="mt-10">
        <Button type="submit" isPending={edit.isPending}>
          Save changes
        </Button>
      </div>
      {edit.isSuccess && <SavedChanges edited={edit.data} reference={record.reference} />}
    </form>
  )
}
