/** An event request's status, as the backend names it (SCRUM-22, ADR-0012). */
export const EVENT_REQUEST_STATUS = {
  DRAFT: 'draft',
  SUBMITTED: 'submitted',
  UNDER_REVIEW: 'under_review',
  AWAITING_CLARIFICATION: 'awaiting_clarification',
  APPROVED: 'approved',
  CONFIRMED: 'confirmed',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
  REJECTED: 'rejected',
} as const

export type EventRequestStatus = (typeof EVENT_REQUEST_STATUS)[keyof typeof EVENT_REQUEST_STATUS]
