import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { Button, ErrorAlert } from '@/components/ui'
import { ROUTES } from '@/config/routes'
import { fieldErrorsOf } from '@/lib/api'

import type { EventRequest } from '../api'
import { useSubmitDraftEventRequest, useUpdateDraftEventRequest } from '../hooks'
import { changesFromForm } from '../requestDetails'
import { useFocusFirstError } from '../useFocusFirstError'

import { EventRequestFields } from './EventRequestFields'

/**
 * One of the organiser's drafts, filled in with what it holds (SCRUM-20 AC3). Saving sends every
 * field again, so an emptied one is forgotten; submitting saves first, then submits, since the
 * backend submits what the draft holds (ADR-0024). Either way the organiser goes back to their
 * list once the backend accepts it.
 */
export function EditDraftForm({ draft }: { draft: EventRequest }) {
  const update = useUpdateDraftEventRequest()
  const submit = useSubmitDraftEventRequest()
  const navigate = useNavigate()
  const [registrationRequired, setRegistrationRequired] = useState(draft.registration_required)
  const formRef = useRef<HTMLFormElement>(null)
  // Only one of the two is ever refused at a time: each clears the other before it starts.
  const error = submit.error ?? update.error
  useFocusFirstError(formRef, error)

  function backToList() {
    void navigate(ROUTES.ORGANISER_HOME)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    update.reset()
    const changes = changesFromForm(new FormData(event.currentTarget), registrationRequired)
    submit.mutate({ reference: draft.reference, changes }, { onSuccess: backToList })
  }

  function handleSave() {
    /* v8 ignore next 3 -- the button is inside the form, so the form is always there */
    if (formRef.current === null) {
      return
    }
    submit.reset()
    const changes = changesFromForm(new FormData(formRef.current), registrationRequired)
    update.mutate({ reference: draft.reference, changes }, { onSuccess: backToList })
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="max-w-2xl space-y-10">
      <ErrorAlert error={error} />
      <EventRequestFields
        fieldErrors={fieldErrorsOf(error)}
        initial={draft}
        registrationRequired={registrationRequired}
        onRegistrationChange={setRegistrationRequired}
      />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" isPending={submit.isPending}>
          Submit request
        </Button>
        <Button type="button" variant="secondary" isPending={update.isPending} onClick={handleSave}>
          Save draft
        </Button>
      </div>
    </form>
  )
}
