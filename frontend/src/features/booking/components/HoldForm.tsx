import type { FormEvent } from 'react'

import { Button, ErrorAlert, TextField } from '@/components/ui'
import { formText } from '@/features/auth/formText'
import { fieldErrorsOf } from '@/lib/api'
import { toBusinessTimeIso } from '@/lib/businessTime'

import type { BookingRequest } from '../api'
import { useChangeHoldExpiry, usePlaceBookingHold } from '../hooks'

interface ExpiryFormProps {
  /** The request's purpose, so the field and the button say which request they belong to. */
  purpose: string
  /** What the button does: place a hold, or move the expiry of one. */
  action: string
  hold: ReturnType<typeof usePlaceBookingHold>
}

/**
 * One expiry, typed in Singapore time, sent with the button. Whether it is in the future and
 * before the event starts is the backend's rule, so its message shows under the field; any other
 * refusal, such as an event with only one venue, shows on its own.
 */
function ExpiryForm({ purpose, action, hold }: ExpiryFormProps) {
  const expiryErrors = fieldErrorsOf(hold.error).expires_at

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const expiresAt = toBusinessTimeIso(formText(new FormData(event.currentTarget), 'expires_at'))
    hold.mutate({ expires_at: expiresAt })
  }

  return (
    <form onSubmit={handleSubmit} className="mt-4 space-y-3">
      <TextField
        label={`Hold expiry for ${purpose}`}
        name="expires_at"
        type="datetime-local"
        required
        hint="In Singapore time, before the event starts."
        errors={expiryErrors}
      />
      {expiryErrors === undefined && <ErrorAlert error={hold.error} />}
      <Button
        type="submit"
        variant="secondary"
        isPending={hold.isPending}
        aria-label={`${action} for ${purpose}`}
      >
        {action}
      </Button>
    </form>
  )
}

/**
 * Hold a waiting request's venue until an expiry, or move the expiry of a request already on
 * hold (SCRUM-75 AC1, AC3, AC4). Which requests can be held is the backend's to say.
 */
export function HoldForm({ request }: { request: BookingRequest }) {
  const place = usePlaceBookingHold(request.id)
  const change = useChangeHoldExpiry(request.id)

  if (request.status === 'on_hold') {
    return <ExpiryForm purpose={request.purpose} action="Change expiry" hold={change} />
  }
  return <ExpiryForm purpose={request.purpose} action="Place hold" hold={place} />
}
