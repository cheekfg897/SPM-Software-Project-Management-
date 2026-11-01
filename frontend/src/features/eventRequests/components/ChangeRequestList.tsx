import { Badge, Button, ErrorAlert } from '@/components/ui'
import { ROLE } from '@/config/roles'
import { attributed } from '@/lib/attributed'
import { formatDateTime } from '@/lib/formatDate'
import { selectSessionUser, useAppSelector } from '@/store'

import type { ChangeRequest } from '../api'
import { CHANGE_REQUEST_STATUS_LABEL, describeRequestedChange } from '../changeRequest'
import type { ChangeableRecord } from '../changeRequest'
import { useWithdrawChangeRequest } from '../hooks'

import { DecideChangeRequest } from './DecideChangeRequest'
import { FactList } from './FactList'

/** The organiser's way to withdraw a Pending request; a refusal shows as the backend gives it. */
function WithdrawChangeRequest({ reference, id }: { reference: string; id: number }) {
  const withdraw = useWithdrawChangeRequest(reference)
  return (
    <div className="mt-4 space-y-3">
      <ErrorAlert error={withdraw.error} />
      <Button
        variant="secondary"
        isPending={withdraw.isPending}
        onClick={() => withdraw.mutate(id)}
      >
        Withdraw change request
      </Button>
    </div>
  )
}

/** Who decided a request and when, e.g. "Approved by Chloe Lim, 5 Oct, 12:00 pm", and why. */
function DecisionOn({ changeRequest }: { changeRequest: ChangeRequest }) {
  const { decided_at: decidedAt, decision_reason: reason } = changeRequest
  if (decidedAt === null) {
    return null
  }
  const label = CHANGE_REQUEST_STATUS_LABEL[changeRequest.status]
  return (
    <>
      <p className="text-ink-faint mt-1 text-sm">
        {attributed(label, changeRequest.decided_by, decidedAt)}
      </p>
      {reason !== null && <p className="text-ink-muted mt-1 text-sm">{reason}</p>}
    </>
  )
}

/**
 * One change request: its status, each change asked for beside the value when it was raised, why,
 * who raised it and when, once withdrawn, when and any note (SCRUM-56 AC4, AC8, AC9), and once
 * decided, who decided it, when and why (SCRUM-57 AC6). The organiser may withdraw a Pending one,
 * and the event's coordinator decide it (SCRUM-57).
 */
function ChangeRequestItem({
  record,
  changeRequest,
}: {
  record: ChangeableRecord
  changeRequest: ChangeRequest
}) {
  const viewer = useAppSelector(selectSessionUser)
  const { withdrawn_at: withdrawnAt } = changeRequest
  const isPending = changeRequest.status === 'pending'
  // Only the event's own organiser may withdraw it; the backend refuses a colleague (AC6).
  const isWithdrawable = viewer?.role === ROLE.EVENT_ORGANISER && isPending
  // A coordinator opens only the records of their own events, so one seeing it may decide it.
  const isDecidable = viewer?.role === ROLE.EVENT_COORDINATOR && isPending
  return (
    <li className="border-line/60 bg-surface/50 rounded-2xl border p-5">
      <Badge>{CHANGE_REQUEST_STATUS_LABEL[changeRequest.status]}</Badge>
      <FactList facts={changeRequest.changes.map(describeRequestedChange)} />
      <p className="text-ink mt-3 whitespace-pre-line">{changeRequest.reason}</p>
      <p className="text-ink-faint mt-1 text-sm">
        {attributed('Raised', changeRequest.raised_by, changeRequest.raised_at)}
      </p>
      {withdrawnAt !== null && (
        <p className="text-ink-faint mt-1 text-sm">Withdrawn {formatDateTime(withdrawnAt)}</p>
      )}
      {changeRequest.withdrawal_note !== null && (
        <p className="text-ink-muted mt-1 text-sm">{changeRequest.withdrawal_note}</p>
      )}
      <DecisionOn changeRequest={changeRequest} />
      {isWithdrawable && (
        <WithdrawChangeRequest reference={record.reference} id={changeRequest.id} />
      )}
      {isDecidable && (
        <div className="mt-4">
          <DecideChangeRequest record={record} changeRequest={changeRequest} />
        </div>
      )}
    </li>
  )
}

/** Every change request raised on the event, oldest first, as the backend sends them (AC4). */
export function ChangeRequestList({ record }: { record: ChangeableRecord }) {
  return (
    <ol className="space-y-3">
      {record.change_requests.map((changeRequest) => (
        <ChangeRequestItem key={changeRequest.id} record={record} changeRequest={changeRequest} />
      ))}
    </ol>
  )
}
