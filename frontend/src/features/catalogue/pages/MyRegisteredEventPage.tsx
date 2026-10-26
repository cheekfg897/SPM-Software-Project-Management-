import { useParams } from 'react-router'

import { PageContainer } from '@/components/layout'
import { ButtonLink, ErrorAlert, Spinner, StatusChip } from '@/components/ui'
import { ROUTES } from '@/config/routes'
import { formatDateTime, formatShortDate, formatTimeRange, formatWeekday } from '@/lib/formatDate'

import type { BookedVenue, MyRegisteredEvent } from '../api'
import { WithdrawAction } from '../components/WithdrawAction'
import { WithdrawalRefusal } from '../components/WithdrawalRefusal'
import { REGISTRATION_STATUS_LABELS } from '../constants'
import { useMyRegisteredEvent, useWithdrawalRefusal } from '../hooks'

/** Before the event arrives, or when it can't be opened, the page has no name for it yet. */
const UNNAMED_TITLE = 'Your event'
/**
 * What the page says while a change has sent the event back to planning (SCRUM-24 AC11, 26 Oct):
 * the venues shown may still change, and the Attendee will hear of it (SCRUM-62).
 */
const BEING_REVIEWED_NOTE =
  'This event’s arrangements are being reviewed and may change. You will be notified of any change.'

/** Each venue the event is booked at, by name and where it is (SCRUM-52). */
function Venues({ venues }: { venues: BookedVenue[] }) {
  if (venues.length === 0) {
    return <p className="text-ink-muted mt-3">No venue is booked for this event.</p>
  }
  return (
    <ul className="mt-3 space-y-3">
      {venues.map((venue) => (
        <li key={`${venue.name} ${venue.location}`}>
          <p className="text-ink font-medium">{venue.name}</p>
          <p className="text-ink-muted text-sm">{venue.location}</p>
        </li>
      ))}
    </ul>
  )
}

/**
 * Withdraw while the backend offers it, saying until when (SCRUM-53). Once it doesn't, the last
 * refusal stays on screen, if there was one, after the event has been read again.
 */
function Withdrawal({ event }: { event: MyRegisteredEvent }) {
  const refusal = useWithdrawalRefusal(event.id)

  if (!event.can_withdraw) {
    return <WithdrawalRefusal error={refusal} />
  }
  return (
    <>
      <p className="text-ink-muted text-sm">
        You can withdraw until {formatDateTime(event.withdrawals_close_at)}.
      </p>
      <WithdrawAction eventId={event.id} name={event.name} />
    </>
  )
}

/** The Attendee's registration: held or withdrawn, and when. */
function Registration({ event }: { event: MyRegisteredEvent }) {
  return (
    <section aria-labelledby="registration-heading" className="mt-10 space-y-3">
      <h2 id="registration-heading" className="font-display text-ink text-xl font-semibold">
        Your registration
      </h2>
      <p className="text-ink font-medium">{REGISTRATION_STATUS_LABELS[event.status]}</p>
      <p className="text-ink-muted text-sm">
        {event.withdrawn_at === null
          ? `You registered on ${formatDateTime(event.registered_at)}.`
          : `You withdrew on ${formatDateTime(event.withdrawn_at)}.`}
      </p>
      <Withdrawal event={event} />
    </section>
  )
}

/**
 * One event the Attendee registered for (SCRUM-24 AC11, docs/adr/0109): what the catalogue shows
 * of any event, its venues, its status and their registration, and Withdraw while the backend
 * offers it. Nothing internal. A Completed or Cancelled event opens read-only with its status,
 * and one a change sent back to planning says its arrangements are being reviewed.
 * This is the page the event link in an Attendee's notifications opens (SCRUM-28).
 */
export function MyRegisteredEventPage() {
  // The route always supplies it; useParams just types it as possibly missing.
  const { reference = '' } = useParams()
  const myEvent = useMyRegisteredEvent(reference)

  if (myEvent.isPending) {
    return (
      <PageContainer title={UNNAMED_TITLE}>
        <p role="status" className="text-ink-muted mt-10 flex items-center gap-2">
          <Spinner /> Loading the event…
        </p>
      </PageContainer>
    )
  }
  if (myEvent.isError) {
    return (
      <PageContainer title={UNNAMED_TITLE}>
        <div className="mt-10">
          <ErrorAlert error={myEvent.error} />
        </div>
      </PageContainer>
    )
  }

  const event = myEvent.data
  return (
    <PageContainer title={event.name}>
      <div className="mt-4">
        <StatusChip status={event.event_status} />
      </div>
      {event.is_being_reviewed && (
        <p className="border-ember/50 bg-ember/15 text-corona mt-6 max-w-2xl rounded-xl border px-4 py-3 text-sm">
          {BEING_REVIEWED_NOTE}
        </p>
      )}
      <p className="text-flare mt-6 font-medium">
        {formatWeekday(event.starts_at)} {formatShortDate(event.starts_at)},{' '}
        {formatTimeRange(event.starts_at, event.ends_at)}
      </p>
      <p className="text-ink mt-4 max-w-2xl">{event.description}</p>
      <section aria-labelledby="venues-heading" className="mt-10">
        <h2 id="venues-heading" className="font-display text-ink text-xl font-semibold">
          Where
        </h2>
        <Venues venues={event.venues} />
      </section>
      <Registration event={event} />
      <ButtonLink to={ROUTES.MY_EVENTS} variant="ghost" className="mt-10">
        Back to My events
      </ButtonLink>
    </PageContainer>
  )
}
