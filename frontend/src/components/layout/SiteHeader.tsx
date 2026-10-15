import { useQueryClient } from '@tanstack/react-query'
import { NavLink, useNavigate } from 'react-router'

import { NotificationBell } from '@/features/notifications/components/NotificationBell'
import { Button, ButtonLink } from '@/components/ui'
import { ROLE } from '@/config/roles'
import { ROUTES } from '@/config/routes'
import { selectSessionUser, signedOut, useAppDispatch, useAppSelector } from '@/store'

import { Logo } from './Logo'

const NAV_LINK_CLASSES =
  'text-sm text-ink-muted transition hover:text-ink aria-[current=page]:text-ink'

function SessionActions() {
  const user = useAppSelector(selectSessionUser)
  const dispatch = useAppDispatch()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  if (user === null) {
    return (
      <>
        <ButtonLink to={ROUTES.LOGIN} variant="ghost">
          Log in
        </ButtonLink>
        <ButtonLink to={ROUTES.SIGN_UP}>Sign up</ButtonLink>
      </>
    )
  }

  // Logging out only forgets the token on this device; the backend can't revoke it yet (SCRUM-89).
  // Leave first: a page only signed-in users may see would otherwise send them to log in the
  // moment the session goes.
  async function logOut() {
    await navigate(ROUTES.HOME, { flushSync: true })
    dispatch(signedOut())
    queryClient.clear()
  }

  return (
    <>
      <NotificationBell />
      <span className="text-ink-muted hidden max-w-40 truncate text-sm sm:inline">
        {user.full_name}
      </span>
      <Button variant="secondary" onClick={() => void logOut()}>
        Log out
      </Button>
    </>
  )
}

/** The main links: the catalogue for everyone, and their own events for an Attendee. */
function MainNav() {
  const user = useAppSelector(selectSessionUser)

  return (
    <nav aria-label="Main" className="flex items-center gap-4 sm:gap-6">
      <NavLink to={ROUTES.EVENTS} className={NAV_LINK_CLASSES}>
        Events
      </NavLink>
      {user?.role === ROLE.ATTENDEE && (
        <NavLink to={ROUTES.MY_EVENTS} className={NAV_LINK_CLASSES}>
          My events
        </NavLink>
      )}
    </nav>
  )
}

export function SiteHeader() {
  return (
    <header className="border-line/60 bg-void/60 fixed inset-x-0 top-0 z-50 border-b backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-4 sm:gap-6 sm:px-6">
        <div className="flex items-center gap-4 sm:gap-8">
          <Logo />
          <MainNav />
        </div>
        <div className="flex items-center gap-2">
          <SessionActions />
        </div>
      </div>
    </header>
  )
}
