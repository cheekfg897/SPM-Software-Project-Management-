import { useState } from 'react'
import type { FormEvent } from 'react'
import type { UseMutationResult } from '@tanstack/react-query'

import { Button, ErrorAlert, TextAreaField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { EventRequest } from '../api'

interface MessageFormProps {
  label: string
  /** The body field the backend reads the text as, so its message shows under the box. */
  field: string
  submitLabel: string
  /** Sends the text typed. Once accepted, the request's status moves on and the form goes. */
  mutation: UseMutationResult<EventRequest, Error, string>
}

/**
 * A text box and the button that sends it: a coordinator's question or an organiser's answer
 * (SCRUM-32). The text is checked by the backend, and its refusal is shown as it comes.
 */
export function MessageForm({ label, field, submitLabel, mutation }: MessageFormProps) {
  const [text, setText] = useState('')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    mutation.mutate(text)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <ErrorAlert error={mutation.error} />
      <TextAreaField
        label={label}
        name={field}
        value={text}
        onChange={(event) => setText(event.target.value)}
        errors={fieldErrorsOf(mutation.error)[field]}
      />
      <Button type="submit" isPending={mutation.isPending}>
        {submitLabel}
      </Button>
    </form>
  )
}
