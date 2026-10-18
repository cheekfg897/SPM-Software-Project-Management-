import { useId, useState } from 'react'
import type { FormEvent } from 'react'

import { Button, ErrorAlert, SelectField, TextAreaField } from '@/components/ui'
import { UNAVAILABILITY_CATEGORIES } from '@/config/unavailabilityCategories'
import { fieldErrorsOf } from '@/lib/api'

import type { Venue } from '../api'
import { useDeactivateVenue, useReactivateVenue } from '../hooks'

import { VenueSection } from './VenueSection'

interface DeactivateQuestionProps {
  venue: Venue
  /** Close the question without deactivating. */
  onKeep: () => void
}

/**
 * Ask why before deactivating (SCRUM-92 AC9, ADR-0067): a category and a note, which the
 * backend requires and passes on to the coordinators it tells. Both go as chosen and typed, so
 * the backend's messages show under the field they are for.
 */
function DeactivateQuestion({ venue, onKeep }: DeactivateQuestionProps) {
  const [category, setCategory] = useState('')
  const [reason, setReason] = useState('')
  const deactivate = useDeactivateVenue(venue.id)
  const fieldErrors = fieldErrorsOf(deactivate.error)
  const headingId = useId()

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    deactivate.mutate({ category, reason })
  }

  return (
    <form
      aria-labelledby={headingId}
      onSubmit={send}
      className="border-danger/40 bg-surface/70 space-y-4 rounded-2xl border p-5"
    >
      <ErrorAlert error={deactivate.error} />
      <p id={headingId} className="font-display text-lg font-semibold tracking-tight">
        Deactivate {venue.name}?
      </p>
      <p className="text-ink-muted text-sm">
        Every booking and request here that has not ended is flagged &quot;Needs Alternative
        Venue&quot;. A confirmed event goes back to Approved, and its coordinator is told why, with
        your note. Reactivating the venue clears the flags, but those events stay Approved.
      </p>
      <SelectField
        label="Why"
        name="category"
        options={UNAVAILABILITY_CATEGORIES}
        emptyLabel="Choose one"
        value={category}
        onChange={(event) => setCategory(event.target.value)}
        errors={fieldErrors.category}
      />
      <TextAreaField
        label="Note"
        name="reason"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        errors={fieldErrors.reason}
      />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" isPending={deactivate.isPending}>
          Deactivate
        </Button>
        <Button variant="ghost" onClick={onKeep}>
          Keep it active
        </Button>
      </div>
    </form>
  )
}

/** Deactivating an active venue (SCRUM-25 AC5): it asks why before anything is sent. */
function DeactivateAction({ venue }: { venue: Venue }) {
  const [isAsking, setIsAsking] = useState(false)

  return (
    <VenueSection
      title="Deactivate venue"
      description="It leaves the venue list and venue search. Bookings already made for it keep it, but each one that has not ended is flagged as needing an alternative venue."
    >
      {isAsking ? (
        <DeactivateQuestion venue={venue} onKeep={() => setIsAsking(false)} />
      ) : (
        <Button variant="secondary" onClick={() => setIsAsking(true)}>
          Deactivate venue
        </Button>
      )}
    </VenueSection>
  )
}

/** Reactivating a deactivated venue (SCRUM-25 AC6), with the backend's refusal if any. */
function ReactivateAction({ venue }: { venue: Venue }) {
  const reactivate = useReactivateVenue(venue.id)

  return (
    <VenueSection
      title="Reactivate venue"
      description="It comes back to the venue list and venue search."
    >
      <div className="space-y-4">
        <ErrorAlert error={reactivate.error} />
        <Button
          variant="secondary"
          isPending={reactivate.isPending}
          onClick={() => reactivate.mutate()}
        >
          Reactivate venue
        </Button>
      </div>
    </VenueSection>
  )
}

/** The status action Venue Staff have on a venue: deactivate it, or reactivate it (ADR-0067). */
export function VenueStatusAction({ venue }: { venue: Venue }) {
  return venue.is_active ? <DeactivateAction venue={venue} /> : <ReactivateAction venue={venue} />
}
