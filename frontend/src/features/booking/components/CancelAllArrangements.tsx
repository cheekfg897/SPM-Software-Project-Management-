import { useState } from 'react'

import { Button, ErrorAlert } from '@/components/ui'

import { useCancelAllArrangements } from '../hooks'

const TITLE = 'Cancel all venue requests'

/**
 * Withdraw every arrangement the event still has, in one go (SCRUM-93). It touches every venue
 * at once, so the coordinator is asked first; the backend refuses if any can't be withdrawn.
 */
export function CancelAllArrangements({ reference }: { reference: string }) {
  const [isConfirming, setIsConfirming] = useState(false)
  const cancelAll = useCancelAllArrangements(reference)

  function keepThem() {
    cancelAll.reset()
    setIsConfirming(false)
  }

  if (!isConfirming) {
    return (
      <section aria-label={TITLE} className="mt-6">
        <Button variant="secondary" onClick={() => setIsConfirming(true)}>
          {TITLE}
        </Button>
      </section>
    )
  }
  return (
    <section
      aria-label={TITLE}
      className="border-danger/40 bg-danger/5 mt-6 space-y-3 rounded-xl border p-4 text-sm"
    >
      <p className="text-ink">
        Every venue request on this event that is still active will be withdrawn.
      </p>
      <ErrorAlert error={cancelAll.error} />
      <div className="flex gap-3">
        <Button
          isPending={cancelAll.isPending}
          onClick={() => cancelAll.mutate(undefined, { onSuccess: () => setIsConfirming(false) })}
        >
          Withdraw them all
        </Button>
        <Button variant="ghost" onClick={keepThem}>
          Keep them
        </Button>
      </div>
    </section>
  )
}
