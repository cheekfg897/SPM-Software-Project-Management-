import { Button, ErrorAlert } from '@/components/ui'
import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { formatShortDate, formatTimeRange } from '@/lib/formatDate'
import { selectSessionUser, useAppSelector } from '@/store'

import type { ReservationReassessment } from '../api'
import { useConfirmReassessment } from '../hooks'

const TITLE = 'Reservations to reassess'
/** Only Technical Support confirm a reservation for the event's period now (SCRUM-60 AC3). */
const CONFIRMER_ROLES: readonly Role[] = [ROLE.TECHNICAL_SUPPORT_STAFF]

/** e.g. "12 Oct, 7:30 pm – 10:00 pm", as the reservation list writes a period. */
function periodText(startsAt: string, endsAt: string): string {
  return `${formatShortDate(startsAt)}, ${formatTimeRange(startsAt, endsAt)}`
}

/** The periods the reservations still hold, each once, e.g. "9 Oct, 7:30 pm – 10:00 pm". */
function heldPeriods(reassessment: ReservationReassessment): string {
  const periods: string[] = []
  for (const reservation of reassessment.reservations) {
    const period = periodText(reservation.starts_at, reservation.ends_at)
    if (!periods.includes(period)) {
      periods.push(period)
    }
  }
  return periods.join('; ')
}

/** What is free for the period now, and the backend's shortfall, in words (AC2). */
function freeText(reassessment: ReservationReassessment): string {
  if (reassessment.shortfall === 0) {
    return `${String(reassessment.available)} free for it, enough for every reserved unit.`
  }
  return `${String(reassessment.available)} free for it: ${String(reassessment.shortfall)} short.`
}

interface ConfirmActionProps {
  reassessment: ReservationReassessment
  onConfirm: (equipmentTypeId: number) => void
  isConfirming: boolean
}

/**
 * What Technical Support do with one type: confirm it where the backend says that settles it
 * (AC3), or record the line's outcome in the form above (AC4, AC12). A type with no line is
 * confirmed even when short, keeping what is free (ADR-0114 decisions 22, 23).
 */
function ConfirmAction({ reassessment, onConfirm, isConfirming }: ConfirmActionProps) {
  const name = reassessment.equipment_type_name
  if (!reassessment.confirmable) {
    return (
      <p className="text-sm">Record the outcome for {name} above; that settles the reservation.</p>
    )
  }
  return (
    <>
      {reassessment.shortfall > 0 && (
        <p className="text-sm">
          Confirming keeps the {reassessment.available} free and releases the rest.
        </p>
      )}
      <Button
        variant="secondary"
        aria-label={`Confirm ${name} for the event's period now`}
        isPending={isConfirming}
        onClick={() => onConfirm(reassessment.equipment_type_id)}
      >
        Confirm for the period now
      </Button>
    </>
  )
}

interface ReassessmentItemProps {
  reassessment: ReservationReassessment
  canConfirm: boolean
  onConfirm: (equipmentTypeId: number) => void
  isConfirming: boolean
}

/** One type's reassessment, and for Technical Support what settles it. */
function ReassessmentItem({
  reassessment,
  canConfirm,
  onConfirm,
  isConfirming,
}: ReassessmentItemProps) {
  const name = reassessment.equipment_type_name
  return (
    <li className="border-line/60 bg-surface/50 space-y-2 rounded-2xl border p-4">
      <p className="font-semibold">
        {name}: {reassessment.reserved_quantity} reserved
      </p>
      <p className="text-ink-muted text-sm">Held for {heldPeriods(reassessment)}</p>
      <p className="text-ink-muted text-sm">
        The event&apos;s period now: {periodText(reassessment.starts_at, reassessment.ends_at)}
      </p>
      <p className={reassessment.shortfall > 0 ? 'text-danger font-semibold' : 'text-sm'}>
        {freeText(reassessment)}
      </p>
      {canConfirm && (
        <ConfirmAction
          reassessment={reassessment}
          onConfirm={onConfirm}
          isConfirming={isConfirming}
        />
      )}
    </li>
  )
}

interface ReassessmentListProps {
  reference: string
  reassessments: ReservationReassessment[]
}

/**
 * What a change to the event's date, time or a line's quantity left to reassess of its
 * reservations (SCRUM-60, ADR-0114): each type's reserved units, the period they still hold, the
 * event's period now and what is free for it, with any shortfall (AC2). Technical Support confirm
 * one for the period now (AC3); a refusal is shown in the backend's words, and the equipment is
 * read again either way. Nothing shows when nothing is marked.
 */
export function ReassessmentList({ reference, reassessments }: ReassessmentListProps) {
  const user = useAppSelector(selectSessionUser)
  const canConfirm = user !== null && CONFIRMER_ROLES.includes(user.role)
  const confirm = useConfirmReassessment(reference)

  if (reassessments.length === 0) {
    return null
  }
  return (
    <section aria-labelledby="reassessments-heading" className="space-y-4">
      <h2 id="reassessments-heading" className="text-xl font-semibold">
        {TITLE}
      </h2>
      <p className="text-ink-muted">
        The event changed after this equipment was reserved. Each reservation stays held where it
        was until it is confirmed for the event&apos;s period now, or its line&apos;s outcome is
        recorded.
      </p>
      <ErrorAlert error={confirm.error} />
      <ul aria-label={TITLE} className="space-y-3">
        {reassessments.map((reassessment) => (
          <ReassessmentItem
            key={reassessment.equipment_type_id}
            reassessment={reassessment}
            canConfirm={canConfirm}
            onConfirm={(equipmentTypeId) => confirm.mutate(equipmentTypeId)}
            isConfirming={confirm.isPending}
          />
        ))}
      </ul>
    </section>
  )
}
