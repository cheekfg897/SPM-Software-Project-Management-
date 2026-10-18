import type { FormEvent } from 'react'

import { Button, ErrorAlert, SelectField, Spinner } from '@/components/ui'
import type { SelectOption } from '@/components/ui'
import { formText } from '@/features/auth/formText'

import type { VenueSummary } from '../api'
import { useSuitability, useVenueSearchFilters, useVenues, useVenueToCheck } from '../hooks'
import type { SearchFilters } from '../searchParams'

const HEADING_ID = 'venue-check-heading'
const REASONS_HEADING = 'Why it is not suitable'

function venueOptions(venues: VenueSummary[]): SelectOption[] {
  return venues.map((venue) => ({ value: String(venue.id), label: venue.name }))
}

/** The backend's answer for one venue: suitable, or not and each reason in its words. */
function SuitabilityAnswer({ venueId, filters }: { venueId: number; filters: SearchFilters }) {
  const { data, error, isPending } = useSuitability(venueId, filters)

  if (error !== null) {
    return <ErrorAlert error={error} />
  }
  if (isPending) {
    return (
      <p className="text-ink-muted flex items-center gap-2">
        <Spinner />
        Checking the venue
      </p>
    )
  }
  if (data.suitable) {
    return <p className="text-ink font-semibold">Suitable for this event</p>
  }
  return (
    <div className="space-y-2">
      <p className="text-danger font-semibold">Not suitable for this event</p>
      <ul aria-label={REASONS_HEADING} className="text-ink-muted list-disc space-y-1 pl-5">
        {/* By place: a need asked for twice is a reason twice. */}
        {data.reasons.map((reason, index) => (
          <li key={index}>{reason.message}</li>
        ))}
      </ul>
    </div>
  )
}

/** Choose a venue to check. The choice goes into the URL, which runs the check. */
function VenuePicker() {
  const venues = useVenues()
  const { venueId, checkVenue } = useVenueToCheck()

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    checkVenue(Number(formText(new FormData(event.currentTarget), 'venue')))
  }

  if (venues.error !== null) {
    return <ErrorAlert error={venues.error} />
  }
  if (venues.isPending) {
    return (
      <p className="text-ink-muted flex items-center gap-2">
        <Spinner />
        Loading venues
      </p>
    )
  }
  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 sm:flex-row sm:items-end">
      <SelectField
        label="Venue"
        name="venue"
        options={venueOptions(venues.data)}
        emptyLabel="Choose a venue"
        required
        defaultValue={venueId === null ? '' : String(venueId)}
        className="sm:w-80"
      />
      <Button type="submit" variant="secondary">
        Check venue
      </Button>
    </form>
  )
}

/**
 * Check one venue against the needs searched for (SCRUM-36), to see why a venue is missing from
 * the results. It covers capacity and requirements, not whether the venue is free (ADR-0017).
 */
export function SuitabilityCheck() {
  const { filters } = useVenueSearchFilters()
  const { venueId } = useVenueToCheck()

  if (filters === null) {
    return null
  }
  return (
    <section className="space-y-4" aria-labelledby={HEADING_ID}>
      <h2 id={HEADING_ID} className="text-xl font-semibold">
        Check a venue
      </h2>
      <p className="text-ink-muted max-w-2xl">
        Checks a venue&apos;s capacity, room layout, facilities and accessibility against the needs
        above. It does not check whether the venue is free.
      </p>
      <VenuePicker />
      {venueId !== null && <SuitabilityAnswer venueId={venueId} filters={filters} />}
    </section>
  )
}
