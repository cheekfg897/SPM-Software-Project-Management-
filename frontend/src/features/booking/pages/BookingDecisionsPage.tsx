import { PageContainer } from '@/components/layout'

import { ApprovedBookings } from '../components/ApprovedBookings'
import { FlaggedBookingQueue } from '../components/FlaggedBookingQueue'
import { PendingDecisionQueue } from '../components/PendingDecisionQueue'

/**
 * Venue Staff's booking requests: the queue waiting for a decision or a hold (SCRUM-43,
 * SCRUM-75), the bookings a change flagged, to reconfirm or reject (SCRUM-59), and the approved
 * bookings whose preparation they record (SCRUM-84, ADR-0080).
 */
export function BookingDecisionsPage() {
  return (
    <PageContainer
      title="Venue booking requests"
      description="Approve a request to book the venue, hold it until an expiry while its event's venues are finalised, or reject it with a reason. The coordinator is told each time."
    >
      <section className="mt-10 space-y-6" aria-labelledby="waiting-heading">
        <h2 id="waiting-heading" className="text-xl font-semibold">
          Waiting for a decision
        </h2>
        <PendingDecisionQueue />
      </section>
      <section className="mt-16 space-y-6" aria-labelledby="flagged-heading">
        <div className="space-y-2">
          <h2 id="flagged-heading" className="text-xl font-semibold">
            Flagged after a change
          </h2>
          <p className="text-ink-muted">
            A change to the event flagged these bookings. Reconfirm each for its new period, which
            starts where the change moved it, or reject it with a reason. The coordinator is told
            either way.
          </p>
        </div>
        <FlaggedBookingQueue />
      </section>
      <section className="mt-16 space-y-6" aria-labelledby="approved-heading">
        <div className="space-y-2">
          <h2 id="approved-heading" className="text-xl font-semibold">
            Approved bookings
          </h2>
          <p className="text-ink-muted">
            Record how far each venue&apos;s preparation has got. The event&apos;s coordinator sees
            it.
          </p>
        </div>
        <ApprovedBookings />
      </section>
    </PageContainer>
  )
}
