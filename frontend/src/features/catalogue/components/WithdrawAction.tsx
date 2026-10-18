import { useState } from 'react'

import { Button, ErrorAlert } from '@/components/ui'
import { textDetailOf } from '@/lib/api'
import { formatDateTime } from '@/lib/formatDate'

import type { MyEvent } from '../api'
import { useWithdrawFromEvent } from '../hooks'

/**
 * Withdraw from one of the Attendee's events, after they confirm, since someone else may take
 * the place (SCRUM-53 AC2). Whether withdrawals are still open is the backend's to say: its
 * refusal is shown with the cut-off it sends (AC3).
 */
export function WithdrawAction({ event }: { event: MyEvent }) {
  const [isConfirming, setIsConfirming] = useState(false)
  const withdrawal = useWithdrawFromEvent()
  const closedAt = textDetailOf(withdrawal.error, 'withdrawal_closed_at')

  return (
    <div className="mt-4 space-y-3">
      <ErrorAlert error={withdrawal.error} />
      {closedAt !== null && (
        <p className="text-ink-muted text-sm">The cut-off was {formatDateTime(closedAt)}.</p>
      )}
      {isConfirming ? (
        <div className="space-y-3">
          <p className="text-ink text-sm">
            Withdraw from {event.name}? Your place goes back to the event and someone else may take
            it.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button
              isPending={withdrawal.isPending}
              onClick={() => withdrawal.mutate(event.event_id)}
            >
              Yes, withdraw
            </Button>
            <Button variant="ghost" onClick={() => setIsConfirming(false)}>
              Keep my place
            </Button>
          </div>
        </div>
      ) : (
        <Button
          variant="secondary"
          aria-label={`Withdraw from ${event.name}`}
          onClick={() => setIsConfirming(true)}
        >
          Withdraw
        </Button>
      )}
    </div>
  )
}
