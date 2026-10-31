import { useState } from 'react'
import type { FormEvent } from 'react'

import { Button, ErrorAlert, TextAreaField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { BookingRequest, CancelBooking } from '../api'
import { useCancelBooking } from '../hooks'

interface CancelBookingFormProps {
  reference: string
  arrangement: BookingRequest
  /** Called when the coordinator keeps the booking, and once it is cancelled. */
  onClose: () => void
}

/**
 * Cancel one approved booking, with a reason (SCRUM-111). It frees the venue and tells Venue
 * Staff, so the coordinator is asked for the reason first. The reason is sent only when one is
 * typed: that one is needed is the backend's rule, and its message shows under the box, as for
 * rejecting an event (ADR-0093). Any other refusal shows above, in the backend's words.
 */
export function CancelBookingForm({ reference, arrangement, onClose }: CancelBookingFormProps) {
  const [reason, setReason] = useState('')
  const cancel = useCancelBooking(reference, arrangement.id)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cancellation: CancelBooking = reason === '' ? {} : { reason }
    cancel.mutate(cancellation, { onSuccess: onClose })
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={`Cancel booking ${arrangement.purpose}`}
      className="border-danger/40 bg-danger/5 mt-4 space-y-4 rounded-xl border p-4"
    >
      <p className="text-ink">
        The venue is freed for this period and Venue Staff are told. The event’s other venues stay
        as they are.
      </p>
      <ErrorAlert error={cancel.error} />
      <TextAreaField
        label="Reason for cancelling"
        name="reason"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        errors={fieldErrorsOf(cancel.error).reason}
      />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" isPending={cancel.isPending}>
          Cancel booking
        </Button>
        <Button variant="ghost" onClick={onClose}>
          Keep it
        </Button>
      </div>
    </form>
  )
}
