import type { ReactNode } from 'react'
import { Navigate, useSearchParams } from 'react-router'

import { NEXT_PARAM } from '@/config/routes'
import { selectSessionUser, useAppSelector } from '@/store'

import { destinationAfterSignIn } from '../roleHome'

/**
 * Shows its page only to someone signed out. Anyone signed in, including someone who has
 * just logged in or signed up here, is sent on: back to `next`, else to their role's home.
 */
export function SignedOutOnly({ children }: { children: ReactNode }) {
  const user = useAppSelector(selectSessionUser)
  const [searchParams] = useSearchParams()

  if (user !== null) {
    const destination = destinationAfterSignIn(user.role, searchParams.get(NEXT_PARAM))
    return <Navigate to={destination} replace />
  }
  return children
}
