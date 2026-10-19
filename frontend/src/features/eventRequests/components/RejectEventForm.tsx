import { useState } from 'react'

import { Button, ErrorAlert, TextAreaField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { EventRecord, Rejection } from '../api'
import { useRejectEvent } from '../hooks'

import { ActionCard } from './ActionCard'

/**
 * Reject an event in planning whose essential arrangements can't be met, with a reason (SCRUM-49
 * AC9, AC10; ADR-0093). It frees the event's venues and equipment and tells the organiser, so
 * the coordinator is asked first. The reason is sent only when one is typed; that one is needed
 * is the backend's rule, and its message shows under the box (as DecisionForm does).
 */
export function RejectEventForm({ record }: { record: EventRecord }) {
  const [reason, setReason] = useState('')
  const [isConfirming, setIsConfirming] = useState(false)
  const reject = useRejectEvent(record.reference)

  function rejectTheEvent() {
    const rejection: Rejection = reason === '' ? {} : { reason }
    reject.mutate(rejection, { onSettled: () => setIsConfirming(false) })
  }

  return (
    <ActionCard
      title="Reject the event"
      description="When an essential venue or equipment arrangement can't be met. The organiser is told, with your reason."
    >
      <ErrorAlert error={reject.error} />
      <TextAreaField
        label="Reason for rejecting"
        name="reason"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        errors={fieldErrorsOf(reject.error).reason}
      />
      {isConfirming ? (
        <div className="border-danger/40 bg-danger/5 space-y-3 rounded-xl border p-4 text-sm">
          <p className="text-ink">
            Its venue bookings and holds are released and its equipment returned.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button isPending={reject.isPending} onClick={rejectTheEvent}>
              Yes, reject the event
            </Button>
            <Button variant="ghost" onClick={() => setIsConfirming(false)}>
              Keep planning
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="secondary" onClick={() => setIsConfirming(true)}>
          Reject event
        </Button>
      )}
    </ActionCard>
  )
}
