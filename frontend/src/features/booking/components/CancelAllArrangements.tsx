import { useState } from 'react'
import type { FormEvent } from 'react'

import { Button, ErrorAlert, TextAreaField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { CancelBooking } from '../api'
import { useCancelAllArrangements } from '../hooks'

const TITLE = 'Cancel all venue requests'

/**
 * Retire every arrangement the event still has, in one go (SCRUM-93 AC6, ADR-0118): a request
 * still waiting is withdrawn and an approved booking cancelled, freeing its venue and telling Venue
 * Staff. It touches every venue at once, so the coordinator is asked first, for a reason. As when
 * cancelling one booking, the reason is sent only when one is typed: that one is needed is the
 * backend's rule, and its message shows under the box. Any other refusal shows above it.
 */
export function CancelAllArrangements({ reference }: { reference: string }) {
  const [isConfirming, setIsConfirming] = useState(false)
  const [reason, setReason] = useState('')
  const cancelAll = useCancelAllArrangements(reference)

  function keepThem() {
    cancelAll.reset()
    setReason('')
    setIsConfirming(false)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cancellation: CancelBooking = reason === '' ? {} : { reason }
    cancelAll.mutate(cancellation, { onSuccess: keepThem })
  }

  if (!isConfirming) {
    return (
      <section aria-label={TITLE} className="mt-6">
        <Button variant="secondary" onClick={() => setIsConfirming(true)}>
          {TITLE}
        </Button>
      </section>
    )
  }
  return (
    <section
      aria-label={TITLE}
      className="border-danger/40 bg-danger/5 mt-6 rounded-xl border p-4 text-sm"
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <p className="text-ink">
          Every venue request on this event that is still active will be withdrawn, and every
          approved booking cancelled: its venue is freed and Venue Staff are told.
        </p>
        <ErrorAlert error={cancelAll.error} />
        <TextAreaField
          label="Reason for cancelling"
          name="reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          errors={fieldErrorsOf(cancelAll.error).reason}
        />
        <div className="flex gap-3">
          <Button type="submit" isPending={cancelAll.isPending}>
            Cancel them all
          </Button>
          <Button variant="ghost" onClick={keepThem}>
            Keep them
          </Button>
        </div>
      </form>
    </section>
  )
}
