import { useId } from 'react'
import type { FormEvent } from 'react'

import { Button, ErrorAlert, SelectField, Spinner, TextAreaField, TextField } from '@/components/ui'
import { UNAVAILABILITY_CATEGORIES } from '@/config/unavailabilityCategories'
import { formText } from '@/features/auth/formText'
import { fieldErrorsOf } from '@/lib/api'
import { formatDateTime, formatShortDate, formatTimeRange } from '@/lib/formatDate'

import type { ConflictingBooking, VenueBlock } from '../api'
import { useBlockVenue, useRemoveVenueBlock, useVenueBlocks } from '../hooks'

import { VenueSection } from './VenueSection'

/** A category's words, e.g. "Equipment failure". */
function categoryLabel(block: VenueBlock): string {
  const category = UNAVAILABILITY_CATEGORIES.find((each) => each.value === block.category)
  return category?.label ?? block.category
}

/** e.g. "Booking 512 for event 101, 10 Nov, 8:30 am – 12:30 pm". */
function conflictText(conflict: ConflictingBooking): string {
  const whose =
    conflict.event_id === null
      ? `Booking ${conflict.booking_id}, with no linked event`
      : `Booking ${conflict.booking_id} for event ${conflict.event_id}`
  const when = formatTimeRange(conflict.start_time, conflict.end_time)
  return `${whose}, ${formatShortDate(conflict.start_time)}, ${when}`
}

/** The confirmed bookings a block just saved cuts into, which stay booked (AC2, ADR-0016). */
function ConflictReport({ conflicts }: { conflicts: ConflictingBooking[] }) {
  const headingId = useId()
  return (
    <section
      aria-labelledby={headingId}
      className="border-ember/50 bg-ember/10 rounded-2xl border p-5 text-sm"
    >
      <p id={headingId} className="text-ink font-medium">
        Blocked. It cuts into these confirmed bookings, which are still booked:
      </p>
      <ul className="text-ink-muted mt-2 space-y-1">
        {conflicts.map((conflict) => (
          <li key={conflict.booking_id}>{conflictText(conflict)}</li>
        ))}
      </ul>
    </section>
  )
}

/**
 * A start, an end, a category and a reason. The times go as typed, in business time, and the
 * category as chosen, so the backend's messages show under the field they are for (ADR-0068).
 */
function BlockForm({ venueId }: { venueId: number }) {
  const block = useBlockVenue(venueId)
  const fieldErrors = fieldErrorsOf(block.error)
  const conflicts = block.data?.conflicting_bookings ?? []

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const formElement = event.currentTarget
    const form = new FormData(formElement)
    block.mutate(
      {
        start_time: formText(form, 'start_time'),
        end_time: formText(form, 'end_time'),
        category: formText(form, 'category'),
        reason: formText(form, 'reason'),
      },
      { onSuccess: () => formElement.reset() },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl space-y-5">
      <ErrorAlert error={block.error} />
      {conflicts.length > 0 && <ConflictReport conflicts={conflicts} />}
      <div className="grid gap-5 sm:grid-cols-2">
        <TextField
          label="Starts"
          name="start_time"
          type="datetime-local"
          errors={fieldErrors.start_time}
        />
        <TextField
          label="Ends"
          name="end_time"
          type="datetime-local"
          errors={fieldErrors.end_time}
        />
      </div>
      <SelectField
        label="Category"
        name="category"
        options={UNAVAILABILITY_CATEGORIES}
        emptyLabel="Choose one"
        errors={fieldErrors.category}
      />
      <TextAreaField label="Reason" name="reason" errors={fieldErrors.reason} />
      <Button type="submit" isPending={block.isPending}>
        Block venue
      </Button>
    </form>
  )
}

interface BlockRowProps {
  block: VenueBlock
  isRemoving: boolean
  onRemove: () => void
}

/** One block, with a way to remove it, which frees the period at once (AC4). */
function BlockRow({ block, isRemoving, onRemove }: BlockRowProps) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="text-ink">{block.reason}</p>
        <p className="text-ink-muted text-sm">
          {categoryLabel(block)}, {formatDateTime(block.start_time)} –{' '}
          {formatDateTime(block.end_time)}
        </p>
      </div>
      <Button
        variant="secondary"
        isPending={isRemoving}
        onClick={onRemove}
        aria-label={`Remove the block for ${block.reason}`}
      >
        Remove
      </Button>
    </li>
  )
}

/** The venue's blocks, in the backend's order (start order), each with a Remove button. */
function BlockList({ venueId }: { venueId: number }) {
  const blocks = useVenueBlocks(venueId)
  const remove = useRemoveVenueBlock(venueId)

  if (blocks.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-3">
        <Spinner />
        Loading blocks…
      </p>
    )
  }
  if (blocks.isError) {
    return <ErrorAlert error={blocks.error} />
  }
  if (blocks.data.length === 0) {
    return <p className="text-ink-muted text-sm">The venue has no blocks.</p>
  }
  return (
    <div className="space-y-3">
      <ErrorAlert error={remove.error} />
      <ul
        aria-label="Blocks"
        className="border-line/70 divide-line/60 divide-y rounded-2xl border px-5"
      >
        {blocks.data.map((block) => (
          <BlockRow
            key={block.id}
            block={block}
            isRemoving={remove.isPending && remove.variables === block.id}
            onRemove={() => remove.mutate(block.id)}
          />
        ))}
      </ul>
    </div>
  )
}

/**
 * Venue Staff's blocks on the venue: a form to add one, and the list to remove them from
 * (SCRUM-34, ADR-0016, ADR-0068). Other staff see blocks only in the calendar.
 */
export function VenueBlocks({ venueId }: { venueId: number }) {
  return (
    <VenueSection
      title="Blocks"
      description="Block the venue for maintenance or internal use. It shows as unavailable, and can't be booked, for that time."
    >
      <div className="space-y-8">
        <BlockForm venueId={venueId} />
        <BlockList venueId={venueId} />
      </div>
    </VenueSection>
  )
}
