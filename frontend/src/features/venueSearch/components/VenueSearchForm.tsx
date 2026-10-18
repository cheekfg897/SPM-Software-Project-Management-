import type { FormEvent } from 'react'

import { Button, SelectField, TextAreaField, TextField } from '@/components/ui'
import { LAYOUT_OPTIONS } from '@/config/roomLayouts'
import { fieldErrorsOf } from '@/lib/api'

import { useVenueSearch, useVenueSearchFilters } from '../hooks'
import { listMessages } from '../listMessages'
import { filtersFrom } from '../searchParams'

/**
 * What the event needs, as filters for the search. Its values come from the URL, so a shared link
 * fills it in, and the backend's messages show under the fields they name.
 */
export function VenueSearchForm() {
  const { filters, applyFilters } = useVenueSearchFilters()
  const { error, isFetching } = useVenueSearch(filters)
  const fieldErrors = fieldErrorsOf(error)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    applyFilters(filtersFrom(new FormData(event.currentTarget)))
  }

  return (
    // Drawn again when the URL's filters change (Back, a shared link), so it shows them.
    <form key={JSON.stringify(filters)} onSubmit={handleSubmit} className="space-y-5">
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <TextField
          label="Date"
          name="date"
          type="date"
          required
          hint="In Singapore time."
          defaultValue={filters?.date}
        />
        <TextField
          label="Start time"
          name="start"
          type="time"
          required
          defaultValue={filters?.start}
          errors={fieldErrors.start_time}
        />
        <TextField
          label="End time"
          name="end"
          type="time"
          required
          defaultValue={filters?.end}
          errors={fieldErrors.end_time}
        />
        <TextField
          label="End date"
          name="end_date"
          type="date"
          hint="Only for an event that ends on a later day."
          defaultValue={filters?.end_date}
        />
      </div>
      <div className="grid gap-5 sm:grid-cols-3">
        <TextField
          label="Minimum capacity"
          name="min_capacity"
          type="number"
          min={1}
          required
          hint="The number of people expected."
          defaultValue={filters?.min_capacity}
          errors={fieldErrors.min_capacity}
        />
        <TextField
          label="Location"
          name="location"
          hint="Venues whose location contains this text."
          defaultValue={filters?.location}
          errors={fieldErrors.location}
        />
        <SelectField
          label="Room layout"
          name="required_layout"
          options={LAYOUT_OPTIONS}
          defaultValue={filters?.required_layout}
          errors={fieldErrors.required_layout}
        />
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <TextAreaField
          label="Facilities"
          name="required_facilities"
          hint="One per line, for example projector."
          defaultValue={filters?.required_facilities.join('\n')}
          errors={listMessages(fieldErrors, 'required_facilities')}
        />
        <TextAreaField
          label="Accessibility requirements"
          name="required_accessibility"
          hint="One per line, for example step-free access."
          defaultValue={filters?.required_accessibility.join('\n')}
          errors={listMessages(fieldErrors, 'required_accessibility')}
        />
      </div>
      <Button type="submit" isPending={isFetching}>
        Search venues
      </Button>
    </form>
  )
}
