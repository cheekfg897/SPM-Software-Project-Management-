import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'

import { catalogueKeys, fetchCatalogue } from './api'
import type { When } from './constants'
import { readCatalogueParams, withPage, withPreset, withRangeEnd, withSearch } from './searchParams'
import type { CatalogueParams, RangeEnd } from './searchParams'

/**
 * The catalogue's filters, read from and written to the page URL. Typing replaces the
 * history entry; choosing a preset or a page adds one, so Back undoes it.
 */
export function useCatalogueParams() {
  const [searchParams, setSearchParams] = useSearchParams()

  return {
    params: readCatalogueParams(searchParams),
    search: (text: string) => {
      setSearchParams((current) => withSearch(current, text), { replace: true })
    },
    choosePreset: (when: When) => {
      setSearchParams((current) => withPreset(current, when))
    },
    setRangeEnd: (end: RangeEnd, value: string) => {
      setSearchParams((current) => withRangeEnd(current, end, value), { replace: true })
    },
    goToPage: (page: number) => {
      setSearchParams((current) => withPage(current, page))
    },
    clearFilters: () => {
      setSearchParams(new URLSearchParams())
    },
  }
}

/** One page of the catalogue for these filters. The last page stays shown while the next loads. */
export function useCatalogue(params: CatalogueParams) {
  return useQuery({
    queryKey: catalogueKeys.list(params),
    queryFn: () => fetchCatalogue(params),
    placeholderData: keepPreviousData,
  })
}
