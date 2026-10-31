import { ErrorAlert } from '@/components/ui'
import { textDetailOf } from '@/lib/api'
import { formatDateTime } from '@/lib/formatDate'

/**
 * Why a withdrawal was refused, in the backend's words, and when withdrawals closed if the
 * backend said (SCRUM-53 AC3). Nothing while there is no refusal.
 */
export function WithdrawalRefusal({ error }: { error: unknown }) {
  const closedAt = textDetailOf(error, 'withdrawal_closed_at')

  return (
    <>
      <ErrorAlert error={error} />
      {closedAt !== null && (
        <p className="text-ink-muted text-sm">The cut-off was {formatDateTime(closedAt)}.</p>
      )}
    </>
  )
}
