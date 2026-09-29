import { useLocation, useNavigate } from 'react-router'

import { Button, ErrorAlert } from '@/components/ui'
import { ROLE } from '@/config/roles'
import { selectSessionUser, useAppSelector } from '@/store'

import type { CatalogueEvent } from '../api'
import { useRegisterForEvent } from '../hooks'
import { loginPathReturningTo } from '../loginRedirect'

function VisitorRegisterButton() {
  const navigate = useNavigate()
  const location = useLocation()

  function goToLogIn() {
    void navigate(loginPathReturningTo(location.pathname + location.search))
  }

  return <Button onClick={goToLogIn}>Register</Button>
}

function AttendeeRegisterButton({ eventId }: { eventId: number }) {
  const registration = useRegisterForEvent()

  return (
    <div className="flex flex-col items-end gap-3">
      <Button isPending={registration.isPending} onClick={() => registration.mutate(eventId)}>
        Register
      </Button>
      <ErrorAlert error={registration.error} />
    </div>
  )
}

/**
 * The Register button on a card. Visitors are sent to log in first. Only Attendees register,
 * so other roles see no button (SCRUM-21). Nothing shows once the event is full or held.
 */
export function RegisterAction({ event }: { event: CatalogueEvent }) {
  const user = useAppSelector(selectSessionUser)

  if (event.is_full || event.is_registered) {
    return null
  }
  if (user === null) {
    return <VisitorRegisterButton />
  }
  if (user.role !== ROLE.ATTENDEE) {
    return null
  }
  return <AttendeeRegisterButton eventId={event.id} />
}
