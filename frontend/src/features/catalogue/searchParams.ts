import { CATALOGUE_PARAM_NAMES, WHEN } from './constants'
import type { CatalogueParamName, When } from './constants'

/**
 * The catalogue's filters live in the page URL, and are sent to the backend exactly as they
 * appear there. These helpers read them and build the next URL; none of them filter anything.
 */

/** The filters in the URL, as strings, keyed by their API names. */
export type CatalogueParams = Partial<Record<CatalogueParamName, string>>

/** A change to the URL: a new value, or null to remove the parameter. */
type ParamChanges = Partial<Record<CatalogueParamName, string | null>>

export type RangeEnd = 'starts_from' | 'starts_to'

export function readCatalogueParams(searchParams: URLSearchParams): CatalogueParams {
  const params: CatalogueParams = {}
  for (const name of CATALOGUE_PARAM_NAMES) {
    const value = searchParams.get(name)
    if (value) {
      params[name] = value
    }
  }
  return params
}

export function hasCustomRange(params: CatalogueParams): boolean {
  return params.starts_from !== undefined || params.starts_to !== undefined
}

/** Whether anything narrows the list. The page number doesn't. */
export function hasFilters(params: CatalogueParams): boolean {
  return params.q !== undefined || params.when !== undefined || hasCustomRange(params)
}

/** Apply `changes`. Any change to the filters goes back to the first page. */
function updated(current: URLSearchParams, changes: ParamChanges): URLSearchParams {
  const next = new URLSearchParams(current)
  if (!('page' in changes)) {
    next.delete('page')
  }
  for (const [name, value] of Object.entries(changes)) {
    if (value) {
      next.set(name, value)
    } else {
      next.delete(name)
    }
  }
  return next
}

export function withSearch(current: URLSearchParams, text: string): URLSearchParams {
  return updated(current, { q: text.trim() })
}

/** Choose a preset. Upcoming is the backend's default, so it's left out of the URL. */
export function withPreset(current: URLSearchParams, when: When): URLSearchParams {
  return updated(current, {
    when: when === WHEN.UPCOMING ? null : when,
    starts_from: null,
    starts_to: null,
  })
}

/** Set one end of a custom range, which replaces any preset. */
export function withRangeEnd(
  current: URLSearchParams,
  end: RangeEnd,
  value: string,
): URLSearchParams {
  return updated(current, { when: null, [end]: value })
}

/** Go to `page`. Page 1 is the backend's default, so it's left out of the URL. */
export function withPage(current: URLSearchParams, page: number): URLSearchParams {
  return updated(current, { page: page === 1 ? null : String(page) })
}
