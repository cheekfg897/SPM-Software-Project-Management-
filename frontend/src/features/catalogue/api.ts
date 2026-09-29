import { apiRequest } from '@/lib/api'

import type { CatalogueParams } from './searchParams'

/** The catalogue API, as docs/adr/0032-event-catalogue-contract.md describes it. */
const CATALOGUE_PATHS = {
  EVENTS: '/api/events/catalogue',
} as const

export interface CatalogueEvent {
  id: number
  reference: string
  name: string
  description: string
  /** ISO date-time with an offset, in business time. */
  starts_at: string
  ends_at: string
  venue: { id: number; name: string } | null
  capacity: number
  places_left: number
  is_full: boolean
  /** Whether the signed-in user holds a place. Always false for a visitor. */
  is_registered: boolean
}

export interface CataloguePage {
  items: CatalogueEvent[]
  page: number
  page_size: number
  total: number
  total_pages: number
}

export const catalogueKeys = {
  all: ['catalogue'] as const,
  list: (params: CatalogueParams) => [...catalogueKeys.all, 'list', params] as const,
}

export function fetchCatalogue(params: CatalogueParams): Promise<CataloguePage> {
  return apiRequest<CataloguePage>(CATALOGUE_PATHS.EVENTS, { query: params })
}
