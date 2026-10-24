import type { UseQueryResult } from '@tanstack/react-query'

import { PageContainer } from '@/components/layout'
import { ErrorAlert, Spinner } from '@/components/ui'

/** Before the record arrives, or when it can't be opened, the page has no event name yet. */
const UNNAMED_TITLE = 'Event request'

/**
 * A record page whose record hasn't arrived: that it is loading, or else the backend's refusal
 * (a "not found" for an event the viewer may not open) as it comes. Pages show it until the
 * record is there.
 */
export function RecordQueryStatus({ query }: { query: UseQueryResult<unknown> }) {
  if (query.isPending) {
    return (
      <PageContainer title={UNNAMED_TITLE}>
        <p role="status" className="text-ink-muted mt-10 flex items-center gap-2">
          <Spinner /> Loading the event…
        </p>
      </PageContainer>
    )
  }
  return (
    <PageContainer title={UNNAMED_TITLE}>
      <div className="mt-10">
        <ErrorAlert error={query.error} />
      </div>
    </PageContainer>
  )
}
