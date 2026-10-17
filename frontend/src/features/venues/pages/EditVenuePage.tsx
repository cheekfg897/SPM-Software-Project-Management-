import { PageContainer } from '@/components/layout'

import { EditVenueForm } from '../components/EditVenueForm'
import { WithVenue } from '../components/WithVenue'

/** Where Venue Staff change a venue's record (SCRUM-25 AC1, SCRUM-67 AC1). */
export function EditVenuePage() {
  return (
    <WithVenue>
      {(venue) => (
        <PageContainer
          title={`Edit ${venue.name}`}
          description="Event Coordinators see your changes as soon as they're saved."
        >
          <EditVenueForm venue={venue} />
        </PageContainer>
      )}
    </WithVenue>
  )
}
