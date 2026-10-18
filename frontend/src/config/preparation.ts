import type { SelectOption } from '@/components/ui'

/**
 * How far staff have got in preparing a venue booking (SCRUM-84) or an equipment reservation
 * (SCRUM-85). The backend's values; every booking and reservation starts `not_started`.
 */
export type PreparationStatus = 'not_started' | 'in_progress' | 'ready'

/** How each status reads on screen. */
export const PREPARATION_STATUS_LABELS: Record<PreparationStatus, string> = {
  not_started: 'Not started',
  in_progress: 'In progress',
  ready: 'Ready',
}

/**
 * A status in words, when `value` is one of the three, e.g. read from an event's history entry;
 * otherwise null.
 */
export function preparationStatusLabel(value: unknown): string | null {
  for (const [status, label] of Object.entries(PREPARATION_STATUS_LABELS)) {
    if (value === status) {
      return label
    }
  }
  return null
}

/** The statuses staff choose from, in the order the work goes. */
export const PREPARATION_STATUS_OPTIONS: readonly SelectOption[] = [
  { value: 'not_started', label: PREPARATION_STATUS_LABELS.not_started },
  { value: 'in_progress', label: PREPARATION_STATUS_LABELS.in_progress },
  { value: 'ready', label: PREPARATION_STATUS_LABELS.ready },
]

/** A booking's or a reservation's preparation, as the backend sends it on each. */
export interface Preparation {
  preparation_status: PreparationStatus
  preparation_notes: string | null
}

/**
 * What staff send to record preparation. Each update states the whole picture: notes left out
 * are cleared (ADR-0049, ADR-0050).
 */
export interface PreparationUpdate {
  /** The status chosen in the form; the backend refuses anything but the three above. */
  status: string
  notes?: string
}
