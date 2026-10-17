import { Button, EmptyState, ErrorAlert, Spinner } from '@/components/ui'

import { useAwaitingSafetyReview } from '../hooks'

import { SafetyReviewCard } from './SafetyReviewCard'

/** The events awaiting the safety check, in the order the backend sent them, or why none show. */
export function SafetyReviewList() {
  const awaiting = useAwaitingSafetyReview()

  if (awaiting.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-3">
        <Spinner />
        Loading events awaiting the safety check…
      </p>
    )
  }
  if (awaiting.isError) {
    return (
      <div className="space-y-4">
        <ErrorAlert error={awaiting.error} />
        <Button variant="secondary" onClick={() => void awaiting.refetch()}>
          Try again
        </Button>
      </div>
    )
  }
  const { events, message } = awaiting.data
  if (events.length === 0) {
    /* v8 ignore next -- the backend always sends a message with an empty list (SCRUM-24 AC11) */
    return <EmptyState message={message ?? ''} />
  }
  return (
    <ul className="space-y-5">
      {events.map((event) => (
        <li key={event.event.reference}>
          <SafetyReviewCard awaiting={event} />
        </li>
      ))}
    </ul>
  )
}
