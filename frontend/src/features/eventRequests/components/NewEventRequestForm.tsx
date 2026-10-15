import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { Button, ErrorAlert } from '@/components/ui'
import { ROUTES } from '@/config/routes'
import { fieldErrorsOf } from '@/lib/api'

import { useSubmitEventRequest } from '../hooks'
import { detailsFromForm } from '../requestDetails'
import { useFocusFirstError } from '../useFocusFirstError'

import { EventRequestFields } from './EventRequestFields'

/**
 * A new event request (SCRUM-19). Once the backend accepts it, the organiser goes back to their
 * list, where it shows with its status and reference (AC5). A refusal keeps what was typed and
 * shows the backend's messages.
 */
export function NewEventRequestForm() {
  const submit = useSubmitEventRequest()
  const navigate = useNavigate()
  // The backend's default when the organiser doesn't say (SCRUM-19).
  const [registrationRequired, setRegistrationRequired] = useState(false)
  const formRef = useRef<HTMLFormElement>(null)
  useFocusFirstError(formRef, submit.error)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const details = detailsFromForm(new FormData(event.currentTarget), registrationRequired)
    submit.mutate(details, { onSuccess: () => void navigate(ROUTES.ORGANISER_HOME) })
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="max-w-2xl space-y-10">
      <ErrorAlert error={submit.error} />
      <EventRequestFields
        fieldErrors={fieldErrorsOf(submit.error)}
        registrationRequired={registrationRequired}
        onRegistrationChange={setRegistrationRequired}
      />
      <Button type="submit" isPending={submit.isPending}>
        Submit request
      </Button>
    </form>
  )
}
