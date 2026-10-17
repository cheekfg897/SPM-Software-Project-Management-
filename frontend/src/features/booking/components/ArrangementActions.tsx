import { useState } from 'react'

import { Button, ErrorAlert } from '@/components/ui'

import type { BookingRequest } from '../api'
import { useWithdrawArrangement } from '../hooks'

import { ChangeArrangementForm } from './ChangeArrangementForm'

interface ArrangementActionsProps {
  reference: string
  arrangement: BookingRequest
}

/**
 * Change or withdraw one of the event's arrangements (SCRUM-93). Which it allows is the
 * backend's call; a refusal is shown here, under the arrangement it was about.
 */
export function ArrangementActions({ reference, arrangement }: ArrangementActionsProps) {
  const [isChanging, setIsChanging] = useState(false)
  const withdraw = useWithdrawArrangement(reference, arrangement.id)

  if (isChanging) {
    return (
      <ChangeArrangementForm
        reference={reference}
        arrangement={arrangement}
        onClose={() => setIsChanging(false)}
      />
    )
  }
  return (
    <div className="mt-3 space-y-3">
      <ErrorAlert error={withdraw.error} />
      <div className="flex gap-3">
        <Button
          variant="secondary"
          aria-label={`Change ${arrangement.purpose}`}
          onClick={() => setIsChanging(true)}
        >
          Change
        </Button>
        <Button
          variant="ghost"
          isPending={withdraw.isPending}
          aria-label={`Withdraw ${arrangement.purpose}`}
          onClick={() => withdraw.mutate()}
        >
          Withdraw
        </Button>
      </div>
    </div>
  )
}
