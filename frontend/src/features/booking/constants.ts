import type { BookingRequestStatus } from './api'

/** How each status reads on screen. */
export const STATUS_LABELS: Record<BookingRequestStatus, string> = {
  pending: 'Pending',
  conflicting: 'Conflicting',
  on_hold: 'On hold',
  approved: 'Approved',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  expired: 'Expired',
  released: 'Released',
}

/**
 * Statuses of an arrangement that is retired: withdrawn by the coordinator, or released when an
 * approved replacement took over (SCRUM-92). It stays on record with nothing left to do.
 */
export const RETIRED_STATUSES: readonly BookingRequestStatus[] = ['withdrawn', 'released']
