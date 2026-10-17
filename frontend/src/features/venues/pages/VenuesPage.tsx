import { PageContainer } from '@/components/layout'

import { VenueList } from '../components/VenueList'

/** The venue catalogue, for every staff role to plan against (SCRUM-25 AC3). */
export function VenuesPage() {
  return (
    <PageContainer
      title="Venues"
      description="Every venue ConnectSphere books, with where it is and how many people it holds."
    >
      <div className="mt-10">
        <VenueList />
      </div>
    </PageContainer>
  )
}
