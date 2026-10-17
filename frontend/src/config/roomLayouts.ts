import type { SelectOption } from '@/components/ui'

/** The room layouts the backend accepts (LayoutType in backend/app/modules/venue/models.py). */
export const LAYOUT_OPTIONS: readonly SelectOption[] = [
  { value: 'classroom', label: 'Classroom' },
  { value: 'theatre', label: 'Theatre' },
  { value: 'boardroom', label: 'Boardroom' },
  { value: 'banquet', label: 'Banquet' },
  { value: 'exhibition', label: 'Exhibition' },
  { value: 'other', label: 'Other' },
]
