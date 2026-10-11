import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

import type { Role } from '@/config/roles'
import { loginPathReturningTo } from '@/config/routes'
import type { LoginRoute } from '@/config/routes'
import { selectSessionUser, useAppSelector } from '@/store'

import { homeFor } from '../roleHome'

interface RequireRoleProps {
  /** Left out, any signed-in user may open the page. */
  allowedRoles?: readonly Role[]
  /** Where to send someone signed out. */
  loginRoute: LoginRoute
  children: ReactNode
}

/**
 * Shows its page only to the roles allowed (or to anyone signed in, with none given). Someone
 * signed out is sent to log in and brought back; someone with another role goes to their own
 * home. The backend still checks every request itself: this only keeps people off pages that
 * would refuse them.
 */
export function RequireRole({ allowedRoles, loginRoute, children }: RequireRoleProps) {
  const user = useAppSelector(selectSessionUser)
  const location = useLocation()

  if (user === null) {
    const here = location.pathname + location.search
    return <Navigate to={loginPathReturningTo(here, loginRoute)} replace />
  }
  if (allowedRoles !== undefined && !allowedRoles.includes(user.role)) {
    return <Navigate to={homeFor(user.role)} replace />
  }
  return children
}
