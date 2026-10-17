import type { FormEvent } from 'react'

import { Button, ErrorAlert, SelectField, TextField } from '@/components/ui'
import { LAYOUT_OPTIONS } from '@/config/roomLayouts'
import { formText } from '@/features/auth/formText'
import { fieldErrorsOf } from '@/lib/api'

import type { RaiseBookingRequest } from '../api'
import { toBusinessTimeIso } from '../businessTime'
import { useRaiseBookingRequest } from '../hooks'

/** The request for the backend; fields left empty are left out so it can fill them in. */
function requestFrom(form: FormData): RaiseBookingRequest {
  const request: RaiseBookingRequest = {
    venue_id: Number(formText(form, 'venue_id')),
    starts_at: toBusinessTimeIso(formText(form, 'starts_at')),
    ends_at: toBusinessTimeIso(formText(form, 'ends_at')),
    purpose: formText(form, 'purpose'),
  }
  const occupancy = formText(form, 'expected_occupancy')
  if (occupancy !== '') {
    request.expected_occupancy = Number(occupancy)
  }
  const layout = formText(form, 'required_layout')
  if (layout !== '') {
    request.required_layout = layout
  }
  const justification = formText(form, 'justification')
  if (justification !== '') {
    request.justification = justification
  }
  return request
}

/** Raise a venue request for the event. The list beside it is read again once it succeeds. */
export function BookingRequestForm({ reference }: { reference: string }) {
  const raise = useRaiseBookingRequest(reference)
  const fieldErrors = fieldErrorsOf(raise.error)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    raise.mutate(requestFrom(new FormData(form)), { onSuccess: () => form.reset() })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <ErrorAlert error={raise.error} />
      <TextField
        label="Venue ID"
        name="venue_id"
        type="number"
        min={1}
        required
        errors={fieldErrors.venue_id}
      />
      <TextField
        label="Starts"
        name="starts_at"
        type="datetime-local"
        required
        hint="In Singapore time."
        errors={fieldErrors.starts_at}
      />
      <TextField
        label="Ends"
        name="ends_at"
        type="datetime-local"
        required
        errors={fieldErrors.ends_at}
      />
      <TextField label="Purpose" name="purpose" required errors={fieldErrors.purpose} />
      <TextField
        label="Expected occupancy"
        name="expected_occupancy"
        type="number"
        min={1}
        hint="Leave empty to use the event's expected attendance."
        errors={fieldErrors.expected_occupancy}
      />
      <SelectField
        label="Required layout"
        name="required_layout"
        options={LAYOUT_OPTIONS}
        errors={fieldErrors.required_layout}
      />
      <TextField
        label="Justification"
        name="justification"
        hint="Needed when the venue does not suit this request's occupancy and layout."
        errors={fieldErrors.justification}
      />
      <Button type="submit" isPending={raise.isPending}>
        Request venue
      </Button>
    </form>
  )
}
