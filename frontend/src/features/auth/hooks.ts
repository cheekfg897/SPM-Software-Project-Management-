import { useMutation, useQuery } from '@tanstack/react-query'

import { selectSessionUser, signedIn, useAppDispatch, useAppSelector } from '@/store'

import { authKeys, fetchCurrentUser, logIn } from './api'

/**
 * Log in. On success the session is saved, and the page the user is on redirects them
 * (see SignedOutOnly), so callers don't navigate themselves.
 */
export function useLogIn() {
  const dispatch = useAppDispatch()
  return useMutation({
    mutationFn: logIn,
    onSuccess: (response) =>
      dispatch(signedIn({ accessToken: response.access_token, user: response.user })),
  })
}

/** The signed-in user as the backend has them now (`GET /api/auth/me`). */
export function useCurrentUser() {
  const sessionUser = useAppSelector(selectSessionUser)
  return useQuery({ queryKey: authKeys.me(sessionUser?.id), queryFn: fetchCurrentUser })
}
