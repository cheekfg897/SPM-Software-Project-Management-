/** The date presets the catalogue accepts as `when` (docs/adr/0032). The backend resolves them. */
export const WHEN = {
  UPCOMING: 'upcoming',
  TODAY: 'today',
  THIS_WEEK: 'this_week',
  THIS_WEEKEND: 'this_weekend',
} as const

export type When = (typeof WHEN)[keyof typeof WHEN]

/** The catalogue's query parameters that live in the page URL, named as the API names them. */
export const CATALOGUE_PARAM_NAMES = ['q', 'when', 'starts_from', 'starts_to', 'page'] as const

export type CatalogueParamName = (typeof CATALOGUE_PARAM_NAMES)[number]

/** Business time, in which the backend sends every date-time (ADR-0009). */
export const BUSINESS_TIME_ZONE = 'Asia/Singapore'
