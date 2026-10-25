import { useState } from 'react'

import { Button } from '@/components/ui'

import { useWithdrawFromEvent } from '../hooks'

import { WithdrawalRefusal } from './WithdrawalRefusal'

interface WithdrawActionProps {
  eventId: number
  /** The event's name, for the button's label and the question it asks. */
  name: string
}

/**
 * Withdraw from one of the Attendee's events, after they confirm, since someone else may take
 * the place (SCRUM-53 AC2). Whether withdrawals are still open is the backend's to say: its
 * refusal is shown with when withdrawals closed, as it sends it (AC4).
 */
export function WithdrawAction({ eventId, name }: WithdrawActionProps) {
  const [isConfirming, setIsConfirming] = useState(false)
  const withdrawal = useWithdrawFromEvent()

  return (
    <div className="mt-4 space-y-3">
      <WithdrawalRefusal error={withdrawal.error} />
      {isConfirming ? (
        <div className="space-y-3">
          <p className="text-ink text-sm">
            Withdraw from {name}? Your place goes back to the event and someone else may take it.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button isPending={withdrawal.isPending} onClick={() => withdrawal.mutate(eventId)}>
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
          aria-label={`Withdraw from ${name}`}
          onClick={() => setIsConfirming(true)}
        >
          Withdraw
        </Button>
      )}
    </div>
  )
}
