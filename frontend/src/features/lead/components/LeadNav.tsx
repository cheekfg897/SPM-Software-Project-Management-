import { NavLink } from 'react-router'

import { ROUTES } from '@/config/routes'

const LINK_CLASSES =
  'rounded-full border border-line px-4 py-1.5 text-sm text-ink-muted transition hover:text-ink ' +
  'aria-[current=page]:border-flare/40 aria-[current=page]:bg-flare/10 aria-[current=page]:text-ink'

/** The Lead's two pages, under each one's title, so the shared header stays the same for all. */
export function LeadNav() {
  return (
    <nav aria-label="Lead" className="mt-6 flex flex-wrap gap-2">
      <NavLink to={ROUTES.LEAD_QUEUE} className={LINK_CLASSES}>
        Unassigned queue
      </NavLink>
      <NavLink to={ROUTES.LEAD_OVERSIGHT} className={LINK_CLASSES}>
        Oversight
      </NavLink>
    </nav>
  )
}
