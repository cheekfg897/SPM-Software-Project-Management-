import { ButtonLink, EmptyState, ErrorAlert, Spinner } from '@/components/ui'
import { ROUTES } from '@/config/routes'

import { useMyEvents } from '../hooks'

import { DayTimeline } from './DayTimeline'
import { MyEventCard } from './MyEventCard'

/**
 * The Attendee's events in one half, on the day timeline, in the backend's order. With none,
 * the backend's own message, and a way to find something to go to (SCRUM-24 AC11).
 */
export function MyEventsResults({ when }: { when: string }) {
  const myEvents = useMyEvents(when)

  if (myEvents.isPending) {
    return (
      <p role="status" className="text-ink-muted flex items-center gap-2">
        <Spinner /> Loading your events…
      </p>
    )
  }
  if (myEvents.isError) {
    return <ErrorAlert error={myEvents.error} />
  }

  // The backend sends a message only with an empty list (docs/adr/0044).
  const { registrations, message } = myEvents.data
  if (message !== undefined) {
    return (
      <EmptyState message={message}>
        <ButtonLink to={ROUTES.EVENTS} className="mt-6">
          Browse events
        </ButtonLink>
      </EmptyState>
    )
  }
  return (
    <DayTimeline
      events={registrations}
      keyOf={(event) => event.event_id}
      renderEvent={(event) => <MyEventCard event={event} />}
    />
  )
}
