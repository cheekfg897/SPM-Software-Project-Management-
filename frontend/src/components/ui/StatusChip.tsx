import type { EventRequestStatus } from '@/config/eventStatus'

interface ChipStyle {
  label: string
  /** Theme-token classes for the chip's border, fill and text. */
  tone: string
}

/**
 * Every status's label and colour. Typed over every status, so one the backend adds later is a
 * type error here until it gets its own. "Answer needed" is the one asking the organiser to act;
 * an Attendee only ever sees confirmed, completed and cancelled (ADR-0044).
 */
const CHIP_BY_STATUS: Record<EventRequestStatus, ChipStyle> = {
  draft: { label: 'Draft', tone: 'border-dashed border-line text-ink-faint' },
  submitted: { label: 'Submitted', tone: 'border-flare/30 bg-flare/10 text-flare' },
  under_review: { label: 'Under review', tone: 'border-nebula/50 bg-nebula/15 text-ink' },
  awaiting_clarification: {
    label: 'Answer needed',
    tone: 'border-ember/50 bg-ember/15 text-corona',
  },
  approved: { label: 'Approved', tone: 'border-success/30 bg-success/10 text-success' },
  confirmed: { label: 'Confirmed', tone: 'border-success/50 bg-success/15 text-success' },
  completed: { label: 'Completed', tone: 'border-line text-ink-muted' },
  cancelled: { label: 'Cancelled', tone: 'border-line text-ink-faint' },
  rejected: { label: 'Rejected', tone: 'border-danger/30 bg-danger/10 text-danger' },
}

/** An event's status as a small coloured label, wherever an event is listed. */
export function StatusChip({ status }: { status: EventRequestStatus }) {
  const { label, tone } = CHIP_BY_STATUS[status]
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${tone}`}
    >
      {label}
    </span>
  )
}
