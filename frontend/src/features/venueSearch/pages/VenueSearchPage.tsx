import { PageContainer } from '@/components/layout'

import { VenueSearchForm } from '../components/VenueSearchForm'
import { VenueSearchResults } from '../components/VenueSearchResults'

/** A coordinator's venue search (SCRUM-35). Everything shown is the backend's answer to the URL. */
export function VenueSearchPage() {
  return (
    <PageContainer
      title="Find a venue"
      description="Enter what the event needs to see the venues that offer it and are free when it runs."
    >
      <div className="mt-10">
        <VenueSearchForm />
      </div>
      <div className="mt-12">
        <VenueSearchResults />
      </div>
    </PageContainer>
  )
}
