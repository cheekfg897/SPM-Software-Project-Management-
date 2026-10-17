import { PageContainer } from '@/components/layout'

import { VenueProfile } from '../components/VenueProfile'
import { WithVenue } from '../components/WithVenue'

/** One venue's page: everything the backend holds about it (SCRUM-25). */
export function VenuePage() {
  return (
    <WithVenue>
      {(venue) => (
        <PageContainer title={venue.name} description={venue.location}>
          <VenueProfile venue={venue} />
        </PageContainer>
      )}
    </WithVenue>
  )
}
