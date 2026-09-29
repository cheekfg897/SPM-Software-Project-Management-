import { PageContainer } from '@/components/layout'

import { CatalogueResults } from '../components/CatalogueResults'
import { SearchBox } from '../components/SearchBox'
import { WhenFilter } from '../components/WhenFilter'

/** The public event catalogue (SCRUM-52). Everything shown is the backend's answer to the URL. */
export function CataloguePage() {
  return (
    <PageContainer
      title="Discover events"
      description="Concerts, talks, workshops and meet-ups across Singapore, confirmed and open for registration."
    >
      <div className="mt-10 space-y-5">
        <SearchBox />
        <WhenFilter />
      </div>
      <div className="mt-12">
        <CatalogueResults />
      </div>
    </PageContainer>
  )
}
