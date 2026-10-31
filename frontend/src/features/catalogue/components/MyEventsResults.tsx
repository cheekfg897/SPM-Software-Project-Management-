import { ButtonLink, EmptyState, ErrorAlert, Spinner } from '@/components/ui'
import { ROUTES } from '@/config/routes'

import type { MyEvent } from '../api'
import { MY_EVENTS_WHEN } from '../constants'
import { useMyEvents } from '../hooks'

import { DayTimeline } from './DayTimeline'
import { MyEventCard } from './MyEventCard'
import { WithdrawAction } from './WithdrawAction'

/**
 * Whether to offer withdrawing: a place still held, at an event under Upcoming. Everything under
 * Past has ended, so its withdrawals have closed (SCRUM-53 AC5, docs/adr/0083).
 */
function canOfferWithdrawal(event: MyEvent, when: string): boolean {
  return when === MY_EVENTS_WHEN.UPCOMING && event.status === 'registered'
}

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
      renderEvent={(event) => (
        <MyEventCard event={event}>
          {canOfferWithdrawal(event, when) && (
            <WithdrawAction eventId={event.event_id} name={event.name} />
          )}
        </MyEventCard>
      )}
    />
  )
}
