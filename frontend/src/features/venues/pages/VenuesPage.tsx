import { PageContainer } from '@/components/layout'
import { ButtonLink } from '@/components/ui'
import { ROUTES } from '@/config/routes'

import { VenueList } from '../components/VenueList'
import { useIsVenueStaff } from '../hooks'

/** The venue catalogue, for every staff role to plan against; Venue Staff add to it (SCRUM-25). */
export function VenuesPage() {
  const isVenueStaff = useIsVenueStaff()

  return (
    <PageContainer
      title="Venues"
      description="Every venue ConnectSphere books, with where it is and how many people it holds."
    >
      {isVenueStaff && (
        <div className="mt-6">
          <ButtonLink to={ROUTES.NEW_VENUE}>Add a venue</ButtonLink>
        </div>
      )}
      <div className="mt-10">
        <VenueList />
      </div>
    </PageContainer>
  )
}
