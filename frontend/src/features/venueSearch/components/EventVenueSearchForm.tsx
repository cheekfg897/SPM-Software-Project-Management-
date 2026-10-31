import { ErrorAlert, Spinner } from '@/components/ui'
import { useEventRequest } from '@/features/eventRequests/hooks'

import { VenueSearchForm } from './VenueSearchForm'

/**
 * The search form opened from an event (SCRUM-90): the event is read from the backend, as its
 * coordinator sees it, and its details fill the form. If it can't be read, the backend's message
 * shows above an empty form, which still searches.
 */
export function EventVenueSearchForm({ reference }: { reference: string }) {
  const record = useEventRequest(reference)

  if (record.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-2">
        <Spinner /> Loading the event…
      </p>
    )
  }
  if (record.isError) {
    return (
      <div className="space-y-5">
        <ErrorAlert error={record.error} />
        <VenueSearchForm />
      </div>
    )
  }
  return <VenueSearchForm event={record.data} />
}
