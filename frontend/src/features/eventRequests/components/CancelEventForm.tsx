import { useState } from 'react'

import { Button, ErrorAlert, TextAreaField } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import type { Cancellation, EventRecord } from '../api'
import { useCancelEvent, useRegistrants } from '../hooks'

import { ActionCard } from './ActionCard'
import { ConfirmStep } from './ConfirmStep'

/** What the card says cancelling does. Nobody is told while no coordinator is assigned. */
function cancelDescription(record: EventRecord): string {
  if (record.coordinator === null) {
    return 'Call the event off. It happens at once.'
  }
  return 'Call the event off. It happens at once, and your coordinator is told your reason.'
}

/** Who is told, in words, from the number of registered attendees the backend counts. */
function attendeesTold(registeredCount: number): string {
  if (registeredCount === 0) {
    return 'No attendee has registered.'
  }
  if (registeredCount === 1) {
    return '1 registered attendee is told.'
  }
  return `${String(registeredCount)} registered attendees are told.`
}

/**
 * Cancel the organiser's event, with a reason (SCRUM-61 AC1; ADR-0122). It takes effect at once
 * and can't be undone, so the page asks first, saying what is released and how many registered
 * attendees are told, as the backend counts them (Product Owner, 29 Oct). The reason is sent
 * only when one is typed; that one is needed is the backend's rule, and its message shows under
 * the box (as RejectEventForm does).
 */
export function CancelEventForm({ record }: { record: EventRecord }) {
  const [reason, setReason] = useState('')
  const [isConfirming, setIsConfirming] = useState(false)
  const cancel = useCancelEvent(record.reference)
  const registrants = useRegistrants(record.reference)

  function cancelTheEvent() {
    const cancellation: Cancellation = reason === '' ? {} : { reason }
    cancel.mutate(cancellation, { onSettled: () => setIsConfirming(false) })
  }

  return (
    <ActionCard title="Cancel the event" description={cancelDescription(record)}>
      <ErrorAlert error={cancel.error} />
      <TextAreaField
        label="Reason for cancelling"
        name="reason"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        errors={fieldErrorsOf(cancel.error).reason}
      />
      {isConfirming ? (
        <ConfirmStep
          confirmLabel="Yes, cancel the event"
          keepLabel="Keep the event"
          isPending={cancel.isPending}
          onConfirm={cancelTheEvent}
          onKeep={() => setIsConfirming(false)}
        >
          <p className="text-ink">
            This can&apos;t be undone. Its venue bookings and holds are released and its reserved
            equipment returned.
            {registrants.isSuccess && ` ${attendeesTold(registrants.data.registered_count)}`}
          </p>
        </ConfirmStep>
      ) : (
        <Button variant="secondary" onClick={() => setIsConfirming(true)}>
          Cancel event
        </Button>
      )}
    </ActionCard>
  )
}
