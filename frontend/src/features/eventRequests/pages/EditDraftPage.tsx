import { useParams } from 'react-router'

import { PageContainer } from '@/components/layout'
import { ErrorAlert, Spinner } from '@/components/ui'

import { EditDraftForm } from '../components/EditDraftForm'
import { useEventRequest } from '../hooks'

/** The draft as the backend holds it, or why it can't be shown (SCRUM-20 AC3). */
function DraftContent({ reference }: { reference: string }) {
  const draft = useEventRequest(reference)

  if (draft.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-2">
        <Spinner /> Loading your draft…
      </p>
    )
  }
  if (draft.isError) {
    return <ErrorAlert error={draft.error} />
  }
  return <EditDraftForm draft={draft.data} />
}

/** Where an Event Organiser finishes one of their drafts, to save again or submit (SCRUM-20). */
export function EditDraftPage() {
  // The route always supplies it; useParams just types it as possibly missing.
  const { reference = '' } = useParams()

  return (
    <PageContainer
      title="Edit draft"
      description="Pick up where you left off. Save it again, or submit it when it's ready."
    >
      <div className="mt-10">
        <DraftContent reference={reference} />
      </div>
    </PageContainer>
  )
}
