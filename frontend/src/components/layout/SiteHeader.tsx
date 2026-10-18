import { useQueryClient } from '@tanstack/react-query'
import { flushSync } from 'react-dom'
import { NavLink, useNavigate } from 'react-router'

import { NotificationBell } from '@/features/notifications/components/NotificationBell'
import { Button, ButtonLink } from '@/components/ui'
import { INTERNAL_ROLES, ROLE } from '@/config/roles'
import { ROUTES } from '@/config/routes'
import { selectSessionUser, signedOut, useAppDispatch, useAppSelector } from '@/store'

import { Logo } from './Logo'

const NAV_LINK_CLASSES =
  'text-sm text-ink-muted transition hover:text-ink aria-[current=page]:text-ink'
/** Where the main links sit for everyone but staff: beside the logo, as far from it as before. */
const BESIDE_THE_LOGO = 'ml-1 gap-4 sm:ml-2 sm:gap-6'
/**
 * Staff's links don't fit beside the logo and Log out on a phone or a tablet, so up to lg they
 * take a row of their own under the bar. Each link stays on one line; on a small phone the row
 * needs closer gaps to fit them all.
 */
const STAFF_LINKS_ROW =
  'col-span-3 row-start-2 gap-3 pb-3 whitespace-nowrap sm:gap-6 lg:col-span-1 lg:col-start-2 lg:row-start-1 lg:ml-2 lg:pb-0'

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
  // Forget the session first, then leave: the front page sends anyone still signed in to their
  // home (SCRUM-6). A page only signed-in users may see starts sending them to log in as the
  // session goes; the router keeps only the latest navigation, so the front page wins.
  async function logOut() {
    flushSync(() => dispatch(signedOut()))
    queryClient.clear()
    await navigate(ROUTES.HOME)
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

/**
 * The main links: the catalogue for everyone, their own events for an Attendee, and for staff
 * the client organisations (SCRUM-66, as "Clients"), the equipment catalogue, which every
 * member of staff reads (SCRUM-27, ADR-0066), and the venue catalogue (ADR-0067).
 */
function MainNav() {
  const user = useAppSelector(selectSessionUser)
  const isStaff = user !== null && INTERNAL_ROLES.includes(user.role)
  const placement = isStaff ? STAFF_LINKS_ROW : BESIDE_THE_LOGO

  return (
    <nav aria-label="Main" className={`flex items-center ${placement}`}>
      <NavLink to={ROUTES.EVENTS} className={NAV_LINK_CLASSES}>
        Events
      </NavLink>
      {user?.role === ROLE.ATTENDEE && (
        <NavLink to={ROUTES.MY_EVENTS} className={NAV_LINK_CLASSES}>
          My events
        </NavLink>
      )}
      {user?.role === ROLE.SAFETY_OFFICER && (
        <NavLink to={ROUTES.SAFETY_REVIEW} className={NAV_LINK_CLASSES}>
          Safety review
        </NavLink>
      )}
      {/* An Event Coordinator's venue search (SCRUM-35, ADR-0073). */}
      {user?.role === ROLE.EVENT_COORDINATOR && (
        <NavLink to={ROUTES.VENUE_SEARCH} className={NAV_LINK_CLASSES}>
          Find a venue
        </NavLink>
      )}
      {isStaff && (
        <>
          <NavLink to={ROUTES.ORGANISATIONS} className={NAV_LINK_CLASSES}>
            Clients
          </NavLink>
          <NavLink to={ROUTES.EQUIPMENT_CATALOGUE} className={NAV_LINK_CLASSES}>
            Equipment
          </NavLink>
          <NavLink to={ROUTES.VENUES} className={NAV_LINK_CLASSES}>
            Venues
          </NavLink>
        </>
      )}
    </nav>
  )
}

export function SiteHeader() {
  return (
    <header className="border-line/60 bg-void/60 fixed inset-x-0 top-0 z-50 border-b backdrop-blur-md">
      <div className="mx-auto grid max-w-6xl grid-cols-[auto_1fr_auto] items-center gap-x-3 px-4 sm:gap-x-6 sm:px-6">
        <div className="flex h-16 items-center">
          <Logo />
        </div>
        <MainNav />
        <div className="col-start-3 flex h-16 items-center gap-2">
          <SessionActions />
        </div>
      </div>
    </header>
  )
}
