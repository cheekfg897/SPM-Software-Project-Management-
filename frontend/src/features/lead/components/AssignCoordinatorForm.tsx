import { useState } from 'react'
import type { SyntheticEvent } from 'react'

import { Button, ErrorAlert, TextField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import { useAssignCoordinator } from '../hooks'

interface AssignCoordinatorFormProps {
  reference: string
}

/**
 * Gives one queued request to the Event Coordinator with the typed email address. There is no
 * list of coordinators to pick from (ADR-0021: user ids are not shown), so the Lead types it.
 */
export function AssignCoordinatorForm({ reference }: AssignCoordinatorFormProps) {
  const [email, setEmail] = useState('')
  const assign = useAssignCoordinator()
  const emailErrors = fieldErrorsOf(assign.error).coordinator_email

  function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    assign.mutate({ reference, coordinator_email: email })
  }

  return (
    <form onSubmit={submit} className="mt-5 space-y-3">
      <TextField
        label="Coordinator email"
        name="coordinator_email"
        type="email"
        autoComplete="off"
        required
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        errors={emailErrors}
      />
      {emailErrors === undefined && <ErrorAlert error={assign.error} />}
      <Button type="submit" isPending={assign.isPending}>
        Assign
      </Button>
    </form>
  )
}
