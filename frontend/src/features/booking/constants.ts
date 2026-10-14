import type { SelectOption } from '@/components/ui'

import type { BookingRequestStatus } from './api'

/** The room layouts the backend accepts (LayoutType in backend/app/modules/venue/models.py). */
export const LAYOUT_OPTIONS: readonly SelectOption[] = [
  { value: 'classroom', label: 'Classroom' },
  { value: 'theatre', label: 'Theatre' },
  { value: 'boardroom', label: 'Boardroom' },
  { value: 'banquet', label: 'Banquet' },
  { value: 'exhibition', label: 'Exhibition' },
  { value: 'other', label: 'Other' },
]

/** How each status reads on screen. The backend adds `on_hold` with SCRUM-75. */
export const STATUS_LABELS: Record<BookingRequestStatus, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
}
