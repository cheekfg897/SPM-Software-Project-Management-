import type { BookingRequestStatus } from './api'

/** How each status reads on screen. The backend adds `on_hold` with SCRUM-75. */
export const STATUS_LABELS: Record<BookingRequestStatus, string> = {
  pending: 'Pending',
  conflicting: 'Conflicting',
  approved: 'Approved',
  rejected: 'Rejected',
}
