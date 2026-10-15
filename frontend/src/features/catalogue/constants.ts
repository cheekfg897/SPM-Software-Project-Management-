/** The date presets the catalogue accepts as `when` (docs/adr/0032). The backend resolves them. */
export const WHEN = {
  UPCOMING: 'upcoming',
  TODAY: 'today',
  THIS_WEEK: 'this_week',
  THIS_WEEKEND: 'this_weekend',
} as const

export type When = (typeof WHEN)[keyof typeof WHEN]

/** The two halves of an Attendee's own events (docs/adr/0044). The backend splits them. */
export const MY_EVENTS_WHEN = {
  UPCOMING: 'upcoming',
  PAST: 'past',
} as const

export type MyEventsWhen = (typeof MY_EVENTS_WHEN)[keyof typeof MY_EVENTS_WHEN]

/** The catalogue's query parameters that live in the page URL, named as the API names them. */
export const CATALOGUE_PARAM_NAMES = ['q', 'when', 'starts_from', 'starts_to', 'page'] as const

export type CatalogueParamName = (typeof CATALOGUE_PARAM_NAMES)[number]
