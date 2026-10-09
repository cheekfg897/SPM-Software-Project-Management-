import { useQuery } from '@tanstack/react-query'

import { selectSessionUser, useAppSelector } from '@/store'

import { eventRequestKeys, fetchMyEventRequests } from './api'

/** The signed-in organiser's event requests, read for whoever is signed in. */
export function useMyEventRequests() {
  const viewer = useAppSelector(selectSessionUser)
  return useQuery({
    queryKey: eventRequestKeys.mine(viewer?.id ?? null),
    queryFn: fetchMyEventRequests,
  })
}
