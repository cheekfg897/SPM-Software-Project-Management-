import { useParams } from 'react-router'

import { PageContainer } from '@/components/layout'
import { ErrorAlert, Spinner } from '@/components/ui'

import { EventRecordView } from '../components/EventRecordView'
import { useEventRequest } from '../hooks'

/** Before the record arrives, or when it can't be opened, the page has no event name yet. */
const UNNAMED_TITLE = 'Event request'

/**
 * One event's record, for an organiser of its organisation or its assigned coordinator, each
 * at their own address (SCRUM-24 AC9, AC10; ADR-0056). Anyone else gets the backend's "not
 * found", shown as it comes.
 */
export function EventRequestPage() {
  // The route always supplies it; useParams just types it as possibly missing.
  const { reference = '' } = useParams()
  const record = useEventRequest(reference)

  if (record.isPending) {
    return (
      <PageContainer title={UNNAMED_TITLE}>
        <p role="status" className="text-ink-muted mt-10 flex items-center gap-2">
          <Spinner /> Loading the event…
        </p>
      </PageContainer>
    )
  }
  if (record.isError) {
    return (
      <PageContainer title={UNNAMED_TITLE}>
        <div className="mt-10">
          <ErrorAlert error={record.error} />
        </div>
      </PageContainer>
    )
  }
  return <EventRecordView record={record.data} />
}
