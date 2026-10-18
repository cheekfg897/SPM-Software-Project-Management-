import { useParams } from 'react-router'

import { PageContainer } from '@/components/layout'
import { ErrorAlert, Spinner } from '@/components/ui'

import { EditEventForm } from '../components/EditEventForm'
import { formatSchedule } from '../formatSchedule'
import { useEventRequest } from '../hooks'

/** The event as the backend holds it, or why it can't be shown, such as not being theirs. */
function EditContent({ reference }: { reference: string }) {
  const record = useEventRequest(reference)

  if (record.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-2">
        <Spinner /> Loading the event…
      </p>
    )
  }
  if (record.isError) {
    return <ErrorAlert error={record.error} />
  }
  return (
    <>
      <p className="font-display text-ink text-xl font-semibold">{record.data.name}</p>
      <p className="text-flare mt-1 text-sm font-medium">{formatSchedule(record.data)}</p>
      <EditEventForm record={record.data} />
    </>
  )
}

/** Where an event's assigned coordinator changes its details while planning it (SCRUM-33). */
export function EditEventPage() {
  // The route always supplies it; useParams just types it as possibly missing.
  const { reference = '' } = useParams()

  return (
    <PageContainer
      title="Edit event details"
      description="Change what you know as plans firm up. Every change is kept in the event's history."
    >
      <div className="mt-10">
        <EditContent reference={reference} />
      </div>
    </PageContainer>
  )
}
