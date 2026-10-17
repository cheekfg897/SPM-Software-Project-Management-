/** The room layouts the backend accepts (LayoutType in backend/app/modules/venue/models.py). */
export const VENUE_LAYOUTS = [
  { value: 'classroom', label: 'Classroom' },
  { value: 'theatre', label: 'Theatre' },
  { value: 'boardroom', label: 'Boardroom' },
  { value: 'banquet', label: 'Banquet' },
  { value: 'exhibition', label: 'Exhibition' },
  { value: 'other', label: 'Other' },
] as const

export type VenueLayout = (typeof VENUE_LAYOUTS)[number]['value']
