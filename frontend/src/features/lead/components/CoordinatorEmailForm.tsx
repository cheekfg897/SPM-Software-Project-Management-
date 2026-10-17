import { useState } from 'react'
import type { SyntheticEvent } from 'react'
import type { UseMutationResult } from '@tanstack/react-query'

import { Button, ErrorAlert, TextField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { AssignedRequest, CoordinatorChoice } from '../api'

interface CoordinatorEmailFormProps {
  reference: string
  /** The event's name, so the field and button say which event they belong to. */
  name: string
  /** What the button does: "Assign" in the queue, "Reassign" on the oversight page. */
  verb: 'Assign' | 'Reassign'
  /** The mutation the form sends, one per card so each shows its own refusal. */
  mutation: UseMutationResult<AssignedRequest, Error, CoordinatorChoice>
}

/**
 * Gives one event to the Event Coordinator with the typed email address. There is no list of
 * coordinators to pick from (ADR-0021: user ids are not shown), so the Lead types it.
 */
export function CoordinatorEmailForm({
  reference,
  name,
  verb,
  mutation,
}: CoordinatorEmailFormProps) {
  const [email, setEmail] = useState('')
  const emailErrors = fieldErrorsOf(mutation.error).coordinator_email

  function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    // The field empties once the backend accepts, since a reassigned event stays on the page.
    mutation.mutate({ reference, coordinator_email: email }, { onSuccess: () => setEmail('') })
  }

  return (
    <form onSubmit={submit} className="mt-5 space-y-3">
      <TextField
        label={`Coordinator email for ${name}`}
        name="coordinator_email"
        type="email"
        autoComplete="off"
        required
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        errors={emailErrors}
      />
      {emailErrors === undefined && <ErrorAlert error={mutation.error} />}
      <Button type="submit" isPending={mutation.isPending} aria-label={`${verb} ${name}`}>
        {verb}
      </Button>
    </form>
  )
}
