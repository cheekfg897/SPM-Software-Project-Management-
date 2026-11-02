import type { FormEvent } from 'react'

import { Button, ErrorAlert, SelectField, TextField } from '@/components/ui'
import { LAYOUT_OPTIONS } from '@/config/roomLayouts'
import { formText } from '@/features/auth/formText'
import { fieldErrorsOf } from '@/lib/api'
import { toBusinessTimeIso } from '@/lib/businessTime'
import { toDateTimeInputValue } from '@/lib/formatDate'

import type { BookingRequest, RaiseBookingRequest } from '../api'
import { useRaiseBookingRequest, useReplacementRequest, useSuggestedRequest } from '../hooks'
import { keepsItsPeriod } from '../replacement'
import type { ReplacementRequest } from '../replacement'

const PERIOD_HINT = 'In Singapore time.'
/** While a replacement keeps the flagged booking's date and times (SCRUM-92 AC6, ADR-0108). */
const LOCKED_PERIOD_HINT = 'Fixed to the booking it replaces. In Singapore time.'

/**
 * What the form starts with: empty, a replacement's venue and its flagged arrangement's needs, or
 * a rejected request's suggested alternative and its needs.
 */
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

/** What an earlier arrangement asked for: its purpose, occupancy and layout. */
function needsOf(arrangement: BookingRequest): FormDefaults {
  return {
    purpose: arrangement.purpose,
    expected_occupancy: String(arrangement.expected_occupancy),
    required_layout: arrangement.required_layout ?? '',
  }
}

/**
 * A replacement starts from the venue chosen and the flagged arrangement's period and needs
 * (SCRUM-92 AC6). A request from a suggestion starts from the venue and period Venue Staff
 * suggested, or the rejected request's own where they suggested none, and its needs (SCRUM-70
 * AC4). Either way the coordinator checks it before sending.
 */
function defaultsFor(
  replacement: ReplacementRequest | null,
  replaced: BookingRequest | undefined,
  suggestedIn: BookingRequest | undefined,
): FormDefaults {
  if (replacement !== null && replaced === undefined) {
    return { venue_id: replacement.venueId }
  }
  if (replacement !== null && replaced !== undefined) {
    return {
      venue_id: replacement.venueId,
      starts_at: toDateTimeInputValue(replaced.starts_at),
      ends_at: toDateTimeInputValue(replaced.ends_at),
      ...needsOf(replaced),
    }
  }
  if (suggestedIn !== undefined) {
    return {
      venue_id: String(suggestedIn.suggested_venue_id ?? suggestedIn.venue_id),
      starts_at: toDateTimeInputValue(suggestedIn.suggested_starts_at ?? suggestedIn.starts_at),
      ends_at: toDateTimeInputValue(suggestedIn.suggested_ends_at ?? suggestedIn.ends_at),
      ...needsOf(suggestedIn),
    }
  }
  return {}
}

interface StartingPointNoteProps {
  /** What the form started from. */
  message: string
  /** The backend's messages about it, e.g. that the arrangement replaced isn't flagged. */
  errors?: string[] | undefined
  stopLabel: string
  onStop: () => void
}

/** Says what the form started from, with the backend's word on it and a way to start afresh. */
function StartingPointNote({ message, errors = [], stopLabel, onStop }: StartingPointNoteProps) {
  return (
    <div className="border-line bg-surface-raised space-y-2 rounded-xl border p-4 text-sm">
      <p className="text-ink">{message}</p>
      {errors.length > 0 && (
        <ul className="text-danger space-y-0.5">
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      )}
      <Button variant="ghost" onClick={onStop}>
        {stopLabel}
      </Button>
    </div>
  )
}

function replacingMessage(replacement: ReplacementRequest, replaced: BookingRequest | undefined) {
  const name = replaced?.purpose ?? `arrangement ${replacement.arrangementId}`
  return `Replacing ${name}, whose venue is unavailable. Approving this request releases it.`
}

function suggestionMessage(suggestedIn: BookingRequest) {
  return (
    `Starting from Venue Staff's suggestion for ${suggestedIn.purpose}. Change anything before ` +
    'you send it; the rejected request stays until you withdraw it.'
  )
}

/** The arrangement the request replaces, if any: the one the URL names, or a rejected replacement's. */
function replacesIdFor(
  replacement: ReplacementRequest | null,
  suggestedIn: BookingRequest | undefined,
): number | null {
  if (replacement !== null) {
    return replacement.arrangementId
  }
  return suggestedIn?.replaces_request_id ?? null
}

/**
 * Raise a venue request for the event, or a replacement for a flagged arrangement when the page
 * URL names one (SCRUM-92 AC6), which keeps the date and times of a booking whose venue is
 * unavailable (ADR-0108), or a request started from the alternative Venue Staff suggested for a
 * rejected one (SCRUM-70 AC4), which the coordinator may change, except a rejected replacement's
 * fixed period. The list beside it is read again
 * once the backend answers.
 */
export function BookingRequestForm({ reference }: { reference: string }) {
  const raise = useRaiseBookingRequest(reference)
  const { replacement, replaced, stopReplacing } = useReplacementRequest(reference)
  const suggestion = useSuggestedRequest(reference)
  const { suggestedIn, stopUsingSuggestion } = suggestion
  const fieldErrors = fieldErrorsOf(raise.error)
  const defaults = defaultsFor(replacement, replaced, suggestedIn)
  // A replacement keeps its period, whether raised afresh or from a rejected one's suggestion.
  const periodLocked = keepsItsPeriod(replaced ?? suggestion.replaced)
  const periodHint = periodLocked ? LOCKED_PERIOD_HINT : PERIOD_HINT
  const replacesId = replacesIdFor(replacement, suggestedIn)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const request = requestFrom(new FormData(form))
    if (replacesId !== null) {
      request.replaces_request_id = replacesId
    }
    raise.mutate(request, {
      onSuccess: () => {
        form.reset()
        if (replacement !== null) {
          stopReplacing()
        }
        if (suggestedIn !== undefined) {
          stopUsingSuggestion()
        }
      },
    })
  }

  return (
    // Drawn again when what it starts from changes, so it starts from that.
    <form key={JSON.stringify(defaults)} onSubmit={handleSubmit} className="space-y-5">
      {replacement !== null && (
        <StartingPointNote
          message={replacingMessage(replacement, replaced)}
          errors={fieldErrors.replaces_request_id}
          stopLabel="Stop replacing"
          onStop={stopReplacing}
        />
      )}
      {replacement === null && suggestedIn !== undefined && (
        <StartingPointNote
          message={suggestionMessage(suggestedIn)}
          errors={fieldErrors.replaces_request_id}
          stopLabel="Stop using the suggestion"
          onStop={stopUsingSuggestion}
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
