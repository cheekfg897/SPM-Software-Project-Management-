import { Button, ErrorAlert } from '@/components/ui'

import type { Venue } from '../api'
import { useDeactivateVenue, useReactivateVenue } from '../hooks'

import { VenueSection } from './VenueSection'

interface StatusActionProps {
  title: string
  /** What the action does, in a line. */
  consequence: string
  mutation: ReturnType<typeof useDeactivateVenue>
}

/** One section: what the action does, the backend's refusal if any, and the button. */
function StatusAction({ title, consequence, mutation }: StatusActionProps) {
  return (
    <VenueSection title={title} description={consequence}>
      <div className="space-y-4">
        <ErrorAlert error={mutation.error} />
        <Button
          variant="secondary"
          isPending={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {title}
        </Button>
      </div>
    </VenueSection>
  )
}

/**
 * Deactivating an active venue (SCRUM-25 AC5) or reactivating a deactivated one (AC6). It asks
 * for no confirmation: either one undoes the other (ADR-0067).
 */
export function VenueStatusAction({ venue }: { venue: Venue }) {
  const deactivate = useDeactivateVenue(venue.id)
  const reactivate = useReactivateVenue(venue.id)

  if (venue.is_active) {
    return (
      <StatusAction
        title="Deactivate venue"
        consequence="It leaves the venue list and venue search. Bookings already made for it keep it."
        mutation={deactivate}
      />
    )
  }
  return (
    <StatusAction
      title="Reactivate venue"
      consequence="It comes back to the venue list and venue search."
      mutation={reactivate}
    />
  )
}
