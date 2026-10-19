import { PageContainer } from '@/components/layout'

import { ReplacementSearchNote } from '../components/ReplacementSearchNote'
import { SuitabilityCheck } from '../components/SuitabilityCheck'
import { VenueSearchForm } from '../components/VenueSearchForm'
import { VenueSearchResults } from '../components/VenueSearchResults'

/**
 * A coordinator's venue search (SCRUM-35) and suitability check (SCRUM-36), which can also find
 * a replacement for a booking whose venue became unavailable (SCRUM-92). Everything shown is the
 * backend's answer to the URL.
 */
export function VenueSearchPage() {
  return (
    <PageContainer
      title="Find a venue"
      description="Enter what the event needs to see the venues that offer it and are free when it runs."
    >
      <ReplacementSearchNote />
      <div className="mt-10">
        <VenueSearchForm />
      </div>
      <div className="mt-12">
        <VenueSearchResults />
      </div>
      <div className="mt-12">
        <SuitabilityCheck />
      </div>
    </PageContainer>
  )
}
