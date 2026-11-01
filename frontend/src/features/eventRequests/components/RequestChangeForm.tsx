import { useRef } from 'react'
import type { FormEvent } from 'react'

import { Button, ErrorAlert, TextAreaField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { EventRecord } from '../api'
import { requestedChange } from '../changeRequest'
import { openingValue } from '../eventEdit'
import { useRaiseChangeRequest } from '../hooks'
import { useFocusFirstError } from '../useFocusFirstError'

import { TimingAndNeedsFields } from './TimingAndNeedsFields'

const SENT_NOTICE =
  'Your change request was sent to the coordinator. It shows under Change requests as Pending.'

/**
 * The organiser's request for a change to their submitted event (SCRUM-56 AC1, AC2), opened with
 * what the event holds. Only what differs is asked for, with why. The event itself stays as it
 * is until the coordinator decides (AC3); the backend checks the request, and its messages show
 * above the form or under the fields they are about (AC6, AC7).
 */
export function RequestChangeForm({ record }: { record: EventRecord }) {
  const raise = useRaiseChangeRequest(record.reference)
  const formRef = useRef<HTMLFormElement>(null)
  useFocusFirstError(formRef, raise.error)
  const errors = fieldErrorsOf(raise.error)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    raise.mutate(requestedChange(new FormData(form), record), { onSuccess: () => form.reset() })
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="max-w-2xl space-y-5">
      <p className="text-ink-muted text-sm">
        The event can't be changed directly once it is submitted. Change what should be different,
        say why, and the coordinator decides. The event keeps its details until then.
      </p>
      <ErrorAlert error={raise.error} />
      {raise.isSuccess && <p className="text-success text-sm">{SENT_NOTICE}</p>}
      <TimingAndNeedsFields record={record} errors={errors} />
      <TextAreaField
        label="Programme notes"
        name="programme_notes"
        defaultValue={openingValue(record, 'programme_notes')}
        errors={errors.programme_notes}
      />
      <TextAreaField label="Why the change is needed" name="reason" errors={errors.reason} />
      <Button type="submit" isPending={raise.isPending}>
        Send change request
      </Button>
    </form>
  )
}
