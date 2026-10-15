import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { Button, ErrorAlert } from '@/components/ui'
import { ROUTES } from '@/config/routes'
import { fieldErrorsOf } from '@/lib/api'

import { useSaveDraftEventRequest, useSubmitEventRequest } from '../hooks'
import { detailsFromForm } from '../requestDetails'
import { useFocusFirstError } from '../useFocusFirstError'

import { EventRequestFields } from './EventRequestFields'

/**
 * A new event request (SCRUM-19), or a draft of one (SCRUM-20). Once the backend accepts it, the
 * organiser goes back to their list, where it shows with its status and reference (AC5). A
 * refusal keeps what was typed and shows the backend's messages.
 */
export function NewEventRequestForm() {
  const submit = useSubmitEventRequest()
  const saveDraft = useSaveDraftEventRequest()
  const navigate = useNavigate()
  // The backend's default when the organiser doesn't say (SCRUM-19).
  const [registrationRequired, setRegistrationRequired] = useState(false)
  const formRef = useRef<HTMLFormElement>(null)
  // Only one of the two is ever refused at a time: each clears the other before it starts.
  const error = submit.error ?? saveDraft.error
  useFocusFirstError(formRef, error)

  function backToList() {
    void navigate(ROUTES.ORGANISER_HOME)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    saveDraft.reset()
    const details = detailsFromForm(new FormData(event.currentTarget), registrationRequired)
    submit.mutate(details, { onSuccess: backToList })
  }

  function handleSaveDraft() {
    /* v8 ignore next 3 -- the button is inside the form, so the form is always there */
    if (formRef.current === null) {
      return
    }
    submit.reset()
    const details = detailsFromForm(new FormData(formRef.current), registrationRequired)
    saveDraft.mutate(details, { onSuccess: backToList })
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="max-w-2xl space-y-10">
      <ErrorAlert error={error} />
      <EventRequestFields
        fieldErrors={fieldErrorsOf(error)}
        registrationRequired={registrationRequired}
        onRegistrationChange={setRegistrationRequired}
      />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" isPending={submit.isPending}>
          Submit request
        </Button>
        <Button
          type="button"
          variant="secondary"
          isPending={saveDraft.isPending}
          onClick={handleSaveDraft}
        >
          Save as draft
        </Button>
      </div>
    </form>
  )
}
