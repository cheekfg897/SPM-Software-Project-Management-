import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'

import { selectSessionUser, useAppSelector } from '@/store'

import { catalogueKeys, fetchCatalogue, fetchMyEvents, registerForEvent } from './api'
import { MY_EVENTS_WHEN } from './constants'
import type { MyEventsWhen, When } from './constants'
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
 * Which half of the Attendee's events the page shows: `when` in the page URL, so a link opens
 * the same half. Upcoming, the backend's default, is left out of the URL.
 */
export function useMyEventsWhen() {
  const [searchParams, setSearchParams] = useSearchParams()

  return {
    when: searchParams.get('when') ?? MY_EVENTS_WHEN.UPCOMING,
    choose: (when: MyEventsWhen) => {
      setSearchParams(when === MY_EVENTS_WHEN.UPCOMING ? {} : { when })
    },
  }
}

/** The signed-in Attendee's upcoming or past events (SCRUM-24 AC7, ADR-0044). */
export function useMyEvents(when: string) {
  const viewer = useAppSelector(selectSessionUser)
  return useQuery({
    /* v8 ignore next -- the page is for signed-in Attendees only (RequireRole), so a viewer is always there */
    queryKey: catalogueKeys.mine(when, viewer?.id ?? null),
    queryFn: () => fetchMyEvents(when),
  })
}

/**
 * Register for an event. Afterwards every catalogue page and the Attendee's own events are read
 * again, so places left, "registered" and the list come from the backend, not guessed here.
 */
export function useRegisterForEvent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: registerForEvent,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: catalogueKeys.all }),
  })
}
