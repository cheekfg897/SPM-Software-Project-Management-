import type { ReactNode } from 'react'

import { Button } from '@/components/ui'

interface ConfirmStepProps {
  /** What going ahead does, for the user to accept before it is sent. */
  children: ReactNode
  confirmLabel: string
  keepLabel: string
  isPending: boolean
  onConfirm: () => void
  onKeep: () => void
}

/**
 * The second step of an action on an event that can't be taken back, such as rejecting it
 * (SCRUM-49) or cancelling it (SCRUM-61): what it does, then go ahead or keep things as they are.
 */
export function ConfirmStep({
  children,
  confirmLabel,
  keepLabel,
  isPending,
  onConfirm,
  onKeep,
}: ConfirmStepProps) {
  return (
    <div className="border-danger/40 bg-danger/5 space-y-3 rounded-xl border p-4 text-sm">
      {children}
      <div className="flex flex-wrap gap-3">
        <Button isPending={isPending} onClick={onConfirm}>
          {confirmLabel}
        </Button>
        <Button variant="ghost" onClick={onKeep}>
          {keepLabel}
        </Button>
      </div>
    </div>
  )
}
