import { useRef } from 'react'
import type { FormEvent, ReactNode } from 'react'

import { ErrorAlert } from '@/components/ui'
import { useFocusFirstError } from '@/features/eventRequests/useFocusFirstError'
import { fieldErrorsOf } from '@/lib/api'

import type { Venue, VenueDetails } from '../api'
import { venueFromForm } from '../venueForm'

import { VenueFields } from './VenueFields'

interface VenueFormProps {
  /** The venue being changed; left out for a new one. */
  initial?: Venue | undefined
  /** The last refusal from the backend, shown above the form and under each field. */
  error: Error | null
  onSubmit: (details: VenueDetails) => void
  /** The form's buttons. */
  children: ReactNode
}

/**
 * The venue form, for adding a venue and for changing one. It sends what was typed and shows
 * the backend's answer; after a refusal it moves to the first field the backend named.
 */
export function VenueForm({ initial, error, onSubmit, children }: VenueFormProps) {
  const formRef = useRef<HTMLFormElement>(null)
  useFocusFirstError(formRef, error)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit(venueFromForm(new FormData(event.currentTarget)))
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="mt-10 max-w-2xl">
      <ErrorAlert error={error} />
      <VenueFields fieldErrors={fieldErrorsOf(error)} initial={initial} />
      <div className="mt-12 flex flex-wrap gap-3">{children}</div>
    </form>
  )
}
