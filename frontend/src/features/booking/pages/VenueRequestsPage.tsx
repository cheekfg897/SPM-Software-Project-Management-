import { useParams } from 'react-router'

import { PageContainer } from '@/components/layout'
import { ErrorAlert, Spinner } from '@/components/ui'

import { BookingRequestForm } from '../components/BookingRequestForm'
import { BookingRequestList } from '../components/BookingRequestList'
import { useBookingRequests } from '../hooks'

/** An event's venue requests, and the form to raise another (SCRUM-42). Coordinators only. */
export function VenueRequestsPage() {
  const { eventId } = useParams()
  const id = Number(eventId)
  const requests = useBookingRequests(id)

  return (
    <PageContainer
      title="Venue requests"
      description="Ask a venue to host this event. Venue Staff are told when you do."
    >
      <section className="mt-10 space-y-4" aria-labelledby="requests-heading">
        <h2 id="requests-heading" className="text-xl font-semibold">
          Requests for this event
        </h2>
        <ErrorAlert error={requests.error} />
        {requests.isPending && (
          <p className="text-ink-muted flex items-center gap-2">
            <Spinner />
            Loading venue requests
          </p>
        )}
        {requests.data !== undefined && <BookingRequestList requests={requests.data} />}
      </section>
      <section className="mt-12 max-w-xl space-y-4" aria-labelledby="raise-heading">
        <h2 id="raise-heading" className="text-xl font-semibold">
          Request a venue
        </h2>
        <BookingRequestForm eventId={id} />
      </section>
    </PageContainer>
  )
}
