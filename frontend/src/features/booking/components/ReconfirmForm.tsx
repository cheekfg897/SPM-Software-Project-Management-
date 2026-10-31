import { useState } from 'react'
import type { FormEvent } from 'react'

import { Button, ErrorAlert, TextField } from '@/components/ui'
import { formText } from '@/features/auth/formText'
import { fieldErrorsOf } from '@/lib/api'
import { toBusinessTimeIso } from '@/lib/businessTime'
import { toDateTimeInputValue } from '@/lib/formatDate'

import type { FlaggedBooking, ReconfirmBooking } from '../api'
import { useReconfirmFlaggedBooking, useRejectFlaggedBooking } from '../hooks'

/**
 * Reconfirm a flagged booking for a period, or reject it, with one reason field for both
 * (SCRUM-59 AC2, AC4, AC5). The period starts as the backend pre-fills it, in Singapore time, and
 * Venue Staff may adjust it. Whether it fits the event, whether a reason is needed and whether
 * the venue is free are the backend's to say: its field messages show under the fields, and any
 * other refusal, such as a clash, shows on its own.
 */
export function ReconfirmForm({ flagged }: { flagged: FlaggedBooking }) {
  const { booking, reconfirm_with: reconfirmWith } = flagged
  const purpose = booking.purpose
  const [reason, setReason] = useState('')
  const reconfirm = useReconfirmFlaggedBooking(booking.id)
  const reject = useRejectFlaggedBooking(booking.id)
  const error = reconfirm.error ?? reject.error
  const fieldErrors = fieldErrorsOf(error)
  const hasFieldErrors = Object.keys(fieldErrors).length > 0

  function handleReconfirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    reject.reset()
    const data = new FormData(event.currentTarget)
    const reconfirmation: ReconfirmBooking = {
      starts_at: toBusinessTimeIso(formText(data, 'starts_at')),
      ends_at: toBusinessTimeIso(formText(data, 'ends_at')),
    }
    reconfirm.mutate(reason === '' ? reconfirmation : { ...reconfirmation, reason })
  }

  function handleReject() {
    reconfirm.reset()
    reject.mutate({ reason })
  }

  return (
    <form onSubmit={handleReconfirm} className="mt-4 space-y-3">
      <TextField
        label={`New start for ${purpose}`}
        name="starts_at"
        type="datetime-local"
        required
        defaultValue={toDateTimeInputValue(reconfirmWith.starts_at)}
        hint="In Singapore time, within the event's new start and end."
        errors={fieldErrors.starts_at}
      />
      <TextField
        label={`New end for ${purpose}`}
        name="ends_at"
        type="datetime-local"
        required
        defaultValue={toDateTimeInputValue(reconfirmWith.ends_at)}
        errors={fieldErrors.ends_at}
      />
      <TextField
        label={`Reason for ${purpose}`}
        name="reason"
        autoComplete="off"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        hint="Needed to reject, and to reconfirm a venue too small for the occupancy."
        errors={fieldErrors.reason}
      />
      {!hasFieldErrors && <ErrorAlert error={error} />}
      <div className="flex gap-3">
        <Button type="submit" isPending={reconfirm.isPending} aria-label={`Reconfirm ${purpose}`}>
          Reconfirm
        </Button>
        <Button
          variant="secondary"
          isPending={reject.isPending}
          aria-label={`Reject ${purpose}`}
          onClick={handleReject}
        >
          Reject
        </Button>
      </div>
    </form>
  )
}
