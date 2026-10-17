import { PageContainer } from '@/components/layout'
import { ButtonLink } from '@/components/ui'
import { editVenuePath } from '@/config/routes'

import type { Venue } from '../api'
import { VenueCalendar } from '../components/VenueCalendar'
import { VenueProfile } from '../components/VenueProfile'
import { VenueStatusAction } from '../components/VenueStatusAction'
import { WithVenue } from '../components/WithVenue'
import { useIsVenueStaff } from '../hooks'

/** The venue, with the actions Venue Staff have on it; other staff read it only (AC4). */
function VenueContent({ venue }: { venue: Venue }) {
  const isVenueStaff = useIsVenueStaff()

  return (
    <PageContainer title={venue.name} description={venue.location}>
      {isVenueStaff && (
        <div className="mt-6">
          <ButtonLink to={editVenuePath(venue.id)} variant="secondary">
            Edit venue
          </ButtonLink>
        </div>
      )}
      <VenueProfile venue={venue} />
      <VenueCalendar venueId={venue.id} />
      {isVenueStaff && <VenueStatusAction venue={venue} />}
    </PageContainer>
  )
}

/** One venue's page: everything the backend holds about it (SCRUM-25). */
export function VenuePage() {
  return <WithVenue>{(venue) => <VenueContent venue={venue} />}</WithVenue>
}
