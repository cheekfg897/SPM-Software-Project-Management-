import { useMutation, useQuery } from '@tanstack/react-query'

import { selectSessionUser, signedIn, useAppDispatch, useAppSelector } from '@/store'

import { authKeys, fetchCurrentUser, logIn, register } from './api'
import type { LoginResponse, Registration } from './api'

/** Save the session a successful log-in returned. */
function useSaveSession() {
  const dispatch = useAppDispatch()
  return (response: LoginResponse) => {
    dispatch(signedIn({ accessToken: response.access_token, user: response.user }))
  }
}

/**
 * Log in. On success the session is saved, and the page the user is on redirects them
 * (see SignedOutOnly), so callers don't navigate themselves.
 */
export function useLogIn() {
  return useMutation({ mutationFn: logIn, onSuccess: useSaveSession() })
}

/** Create the account, then log in with the same details (SCRUM-65 AC5). */
async function registerThenLogIn(registration: Registration): Promise<LoginResponse> {
  await register(registration)
  return logIn({ email: registration.email, password: registration.password })
}

/** Sign up. Like useLogIn, success saves the session and the page redirects. */
export function useSignUp() {
  return useMutation({ mutationFn: registerThenLogIn, onSuccess: useSaveSession() })
}

/** The signed-in user as the backend has them now (`GET /api/auth/me`). */
export function useCurrentUser() {
  const sessionUser = useAppSelector(selectSessionUser)
  return useQuery({ queryKey: authKeys.me(sessionUser?.id), queryFn: fetchCurrentUser })
}
