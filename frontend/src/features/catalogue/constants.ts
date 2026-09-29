/** The date presets the catalogue accepts as `when` (docs/adr/0032). The backend resolves them. */
export const WHEN = {
  UPCOMING: 'upcoming',
  TODAY: 'today',
  THIS_WEEK: 'this_week',
  THIS_WEEKEND: 'this_weekend',
} as const

export type When = (typeof WHEN)[keyof typeof WHEN]
