import type { ReactNode } from 'react'
import { Navigate, useParams } from 'react-router'

import { ROLE, STAFF_RECORD_READER_ROLES } from '@/config/roles'
import { organiserRequestPath, staffEventPath } from '@/config/routes'
import { MyRegisteredEventPage } from '@/features/catalogue/pages/MyRegisteredEventPage'
import { selectSessionUser, useAppSelector } from '@/store'

/**
 * `/events/<reference>` is the address every notification's event link opens, whoever it is for
 * (SCRUM-28 AC1), so each role opens its own view of the event from here (docs/adr/0109). An
 * Attendee sees their own event here (SCRUM-24 AC11). An Organiser goes to their organisation's
 * request, and Venue Staff, Technical Support, the Safety Officer and the Lead to the read-only
 * staff record (SCRUM-24 AC9, AC10). The coordinator, and a visitor, get `children`: the
 * coordinator's record, which asks a visitor to log in.
 */
export function EventPageForRole({ children }: { children: ReactNode }) {
  const user = useAppSelector(selectSessionUser)
  // The route always supplies it; useParams just types it as possibly missing.
  const { reference = '' } = useParams()

  if (user === null) {
    return children
  }
  if (user.role === ROLE.ATTENDEE) {
    return <MyRegisteredEventPage />
  }
  if (user.role === ROLE.EVENT_ORGANISER) {
    return <Navigate to={organiserRequestPath(reference)} replace />
  }
  if (STAFF_RECORD_READER_ROLES.includes(user.role)) {
    return <Navigate to={staffEventPath(reference)} replace />
  }
  return children
}
