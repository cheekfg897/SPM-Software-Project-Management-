import type { ReactNode } from 'react'

import { ROLE } from '@/config/roles'
import { MyRegisteredEventPage } from '@/features/catalogue/pages/MyRegisteredEventPage'
import { selectSessionUser, useAppSelector } from '@/store'

/**
 * `/events/<reference>` is the address every notification's event link opens (SCRUM-28). An
 * Attendee opens their own event there (SCRUM-24 AC11, docs/adr/0109); anyone else gets
 * `children`, the page that was already at this address.
 */
export function AttendeeEventOr({ children }: { children: ReactNode }) {
  const user = useAppSelector(selectSessionUser)

  if (user?.role === ROLE.ATTENDEE) {
    return <MyRegisteredEventPage />
  }
  return children
}
