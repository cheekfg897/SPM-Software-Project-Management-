import type { FormEvent } from 'react'

import { Button, ErrorAlert, SelectField, TextField } from '@/components/ui'
import { LAYOUT_OPTIONS } from '@/config/roomLayouts'
import { formText } from '@/features/auth/formText'
import { fieldErrorsOf } from '@/lib/api'
import { toBusinessTimeIso } from '@/lib/businessTime'
import { toDateTimeInputValue } from '@/lib/formatDate'

import type { BookingRequest, RaiseBookingRequest } from '../api'
import { useRaiseBookingRequest, useReplacementRequest } from '../hooks'
import { keepsItsPeriod } from '../replacement'
import type { ReplacementRequest } from '../replacement'

const PERIOD_HINT = 'In Singapore time.'
/** While a replacement keeps the flagged booking's date and times (SCRUM-92 AC6, ADR-0108). */
const LOCKED_PERIOD_HINT = 'Fixed to the booking it replaces. In Singapore time.'

/** What the form starts with: empty, or a replacement's venue and its flagged arrangement's needs. */
type FormDefaults = Partial<
  Record<
    'venue_id' | 'starts_at' | 'ends_at' | 'purpose' | 'expected_occupancy' | 'required_layout',
    string
  >
>

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

/**
 * A replacement starts from the venue chosen and the flagged arrangement's period, purpose,
 * occupancy and layout, for the coordinator to check before sending.
 */
function defaultsFor(
  replacement: ReplacementRequest | null,
  replaced: BookingRequest | undefined,
): FormDefaults {
  if (replacement === null) {
    return {}
  }
  if (replaced === undefined) {
    return { venue_id: replacement.venueId }
  }
  return {
    venue_id: replacement.venueId,
    starts_at: toDateTimeInputValue(replaced.starts_at),
    ends_at: toDateTimeInputValue(replaced.ends_at),
    purpose: replaced.purpose,
    expected_occupancy: String(replaced.expected_occupancy),
    required_layout: replaced.required_layout ?? '',
  }
}

interface ReplacementNoteProps {
  /** The flagged arrangement's name: its purpose, or its id when the list doesn't hold it. */
  name: string
  /** The backend's messages about the arrangement named, e.g. that it isn't flagged. */
  errors: string[] | undefined
  onStop: () => void
}

/** Says the request replaces a flagged arrangement, with the backend's word on that link. */
function ReplacementNote({ name, errors = [], onStop }: ReplacementNoteProps) {
  return (
    <div className="border-line bg-surface-raised space-y-2 rounded-xl border p-4 text-sm">
      <p className="text-ink">
        Replacing {name}, whose venue is unavailable. Approving this request releases it.
      </p>
      {errors.length > 0 && (
        <ul className="text-danger space-y-0.5">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
      <Button variant="ghost" onClick={onStop}>
        Stop replacing
      </Button>
    </div>
  )
}

/**
 * Raise a venue request for the event, or a replacement for a flagged arrangement when the page
 * URL names one (SCRUM-92 AC6), which keeps the date and times of a booking whose venue is
 * unavailable (ADR-0108). The list beside it is read again once the backend answers.
 */
export function BookingRequestForm({ reference }: { reference: string }) {
  const raise = useRaiseBookingRequest(reference)
  const { replacement, replaced, stopReplacing } = useReplacementRequest(reference)
  const fieldErrors = fieldErrorsOf(raise.error)
  const defaults = defaultsFor(replacement, replaced)
  const periodLocked = keepsItsPeriod(replaced)
  const periodHint = periodLocked ? LOCKED_PERIOD_HINT : PERIOD_HINT

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const request = requestFrom(new FormData(form))
    if (replacement !== null) {
      request.replaces_request_id = replacement.arrangementId
    }
    raise.mutate(request, {
      onSuccess: () => {
        form.reset()
        if (replacement !== null) {
          stopReplacing()
        }
      },
    })
  }

  return (
    // Drawn again when the replacement or its arrangement changes, so it starts from them.
    <form key={JSON.stringify(defaults)} onSubmit={handleSubmit} className="space-y-5">
      {replacement !== null && (
        <ReplacementNote
          name={replaced?.purpose ?? `arrangement ${replacement.arrangementId}`}
          errors={fieldErrors.replaces_request_id}
          onStop={stopReplacing}
        />
      )}
      <ErrorAlert error={raise.error} />
      <TextField
        label="Venue ID"
        name="venue_id"
        type="number"
        min={1}
        required
        defaultValue={defaults.venue_id}
        errors={fieldErrors.venue_id}
      />
      <TextField
        label="Starts"
        name="starts_at"
        type="datetime-local"
        required
        readOnly={periodLocked}
        hint={periodHint}
        defaultValue={defaults.starts_at}
        errors={fieldErrors.starts_at}
      />
      <TextField
        label="Ends"
        name="ends_at"
        type="datetime-local"
        required
        readOnly={periodLocked}
        hint={periodHint}
        defaultValue={defaults.ends_at}
        errors={fieldErrors.ends_at}
      />
      <TextField
        label="Purpose"
        name="purpose"
        required
        defaultValue={defaults.purpose}
        errors={fieldErrors.purpose}
      />
      <TextField
        label="Expected occupancy"
        name="expected_occupancy"
        type="number"
        min={1}
        hint="Leave empty to use the event's expected attendance."
        defaultValue={defaults.expected_occupancy}
        errors={fieldErrors.expected_occupancy}
      />
      <SelectField
        label="Required layout"
        name="required_layout"
        options={LAYOUT_OPTIONS}
        defaultValue={defaults.required_layout}
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
