import { useState } from 'react'

import { Button, ErrorAlert } from '@/components/ui'

import type { BookingRequest } from '../api'
import { useWithdrawArrangement } from '../hooks'

import { CancelBookingForm } from './CancelBookingForm'
import { ChangeArrangementForm } from './ChangeArrangementForm'

interface ArrangementActionsProps {
  reference: string
  arrangement: BookingRequest
}

/** Which form, if any, is open in place of the buttons. */
type OpenForm = 'none' | 'change' | 'cancel'

/**
 * Change or withdraw one of the event's arrangements (SCRUM-93), or cancel it once it is an
 * approved booking (SCRUM-111). Which it allows is the backend's call; a refusal is shown here,
 * under the arrangement it was about. Cancelling is offered only for an approved booking, the
 * one thing it applies to: one not yet approved is withdrawn instead.
 */
export function ArrangementActions({ reference, arrangement }: ArrangementActionsProps) {
  const [openForm, setOpenForm] = useState<OpenForm>('none')
  const withdraw = useWithdrawArrangement(reference, arrangement.id)
  const closeForm = () => setOpenForm('none')

  if (openForm === 'change') {
    return (
      <ChangeArrangementForm reference={reference} arrangement={arrangement} onClose={closeForm} />
    )
  }
  if (openForm === 'cancel') {
    return <CancelBookingForm reference={reference} arrangement={arrangement} onClose={closeForm} />
  }
  return (
    <div className="mt-3 space-y-3">
      <ErrorAlert error={withdraw.error} />
      <div className="flex flex-wrap gap-3">
        <Button
          variant="secondary"
          aria-label={`Change ${arrangement.purpose}`}
          onClick={() => setOpenForm('change')}
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
        {arrangement.status === 'approved' && (
          <Button
            variant="ghost"
            aria-label={`Cancel booking ${arrangement.purpose}`}
            onClick={() => setOpenForm('cancel')}
          >
            Cancel booking
          </Button>
        )}
      </div>
    </div>
  )
}
