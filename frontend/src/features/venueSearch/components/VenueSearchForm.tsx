import type { FormEvent } from 'react'

import { Button, SelectField, TextAreaField, TextField } from '@/components/ui'
import { LAYOUT_OPTIONS } from '@/config/roomLayouts'
import type { EventRequest } from '@/features/eventRequests/api'
import { fieldErrorsOf } from '@/lib/api'

import { filtersFromEvent } from '../eventFilters'
import { useVenueSearch, useVenueSearchFilters } from '../hooks'
import { listMessages } from '../listMessages'
import { filtersFrom } from '../searchParams'

import { EventRequirementsNote } from './EventRequirementsNote'

interface VenueSearchFormProps {
  /** The event the search was opened from, whose details fill the form until it is searched. */
  event?: EventRequest
}

/**
 * What the event needs, as filters for the search. Its values come from the URL, so a shared link
 * fills it in, and the backend's messages show under the fields they name. Opened from an event
 * with nothing searched yet, the event's recorded details fill it in instead (SCRUM-90), and
 * its own words sit beside the filters they could not fill.
 */
export function VenueSearchForm({ event }: VenueSearchFormProps) {
  const { filters, applyFilters } = useVenueSearchFilters()
  const { error, isFetching } = useVenueSearch(filters)
  const fieldErrors = fieldErrorsOf(error)
  const shown = filters ?? (event === undefined ? null : filtersFromEvent(event))

  function handleSubmit(submitted: FormEvent<HTMLFormElement>) {
    submitted.preventDefault()
    applyFilters(filtersFrom(new FormData(submitted.currentTarget)))
  }

  return (
    // Drawn again when the URL's filters change (Back, a shared link), so it shows them.
    <form key={JSON.stringify(shown)} onSubmit={handleSubmit} className="space-y-5">
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <TextField
          label="Date"
          name="date"
          type="date"
          required
          hint="In Singapore time."
          defaultValue={shown?.date}
        />
        <TextField
          label="Start time"
          name="start"
          type="time"
          required
          defaultValue={shown?.start}
          errors={fieldErrors.start_time}
        />
        <TextField
          label="End time"
          name="end"
          type="time"
          required
          defaultValue={shown?.end}
          errors={fieldErrors.end_time}
        />
        <TextField
          label="End date"
          name="end_date"
          type="date"
          hint="Only for an event that ends on a later day."
          defaultValue={shown?.end_date}
        />
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <TextField
          label="Minimum capacity"
          name="min_capacity"
          type="number"
          min={1}
          required
          hint="The number of people expected."
          defaultValue={shown?.min_capacity}
          errors={fieldErrors.min_capacity}
        />
        <TextField
          label="Location"
          name="location"
          hint="Venues whose location contains this text."
          defaultValue={shown?.location}
          errors={fieldErrors.location}
        />
      </div>
      {event !== undefined && <EventRequirementsNote event={event} />}
      <div className="grid gap-5 sm:grid-cols-3">
        <SelectField
          label="Room layout"
          name="required_layout"
          options={LAYOUT_OPTIONS}
          defaultValue={shown?.required_layout}
          errors={fieldErrors.required_layout}
        />
        <TextAreaField
          label="Facilities"
          name="required_facilities"
          hint="One per line, for example projector."
          defaultValue={shown?.required_facilities.join('\n')}
          errors={listMessages(fieldErrors, 'required_facilities')}
        />
        <TextAreaField
          label="Accessibility requirements"
          name="required_accessibility"
          hint="One per line, for example step-free access."
          defaultValue={shown?.required_accessibility.join('\n')}
          errors={listMessages(fieldErrors, 'required_accessibility')}
        />
      </div>
      <Button type="submit" isPending={isFetching}>
        Search venues
      </Button>
    </form>
  )
}
