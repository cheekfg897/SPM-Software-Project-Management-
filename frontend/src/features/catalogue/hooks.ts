import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'

import { selectSessionUser, useAppSelector } from '@/store'

import { catalogueKeys, fetchCatalogue, registerForEvent } from './api'
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
  const viewer = useAppSelector(selectSessionUser)
  return useQuery({
    queryKey: catalogueKeys.list(params, viewer?.id ?? null),
    queryFn: () => fetchCatalogue(params),
    placeholderData: keepPreviousData,
  })
}

/**
 * Register for an event. Afterwards every catalogue page is read again, so places left and
 * "registered" come from the backend rather than being guessed here.
 */
export function useRegisterForEvent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: registerForEvent,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: catalogueKeys.all }),
  })
}
