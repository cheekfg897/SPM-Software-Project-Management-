import type { BookingRequestStatus } from './api'

/** How each status reads on screen. */
export const STATUS_LABELS: Record<BookingRequestStatus, string> = {
  pending: 'Pending',
  conflicting: 'Conflicting',
  on_hold: 'On hold',
  approved: 'Approved',
  rejected: 'Rejected',
  expired: 'Expired',
  released: 'Released',
}
