import { ROLE } from '@/config/roles'
import { ROUTES } from '@/config/routes'

import { destinationAfterSignIn, homeFor } from './roleHome'

describe('SCRUM-6 landing view for each role', () => {
  it.each([
    [ROLE.ATTENDEE, ROUTES.EVENTS],
    [ROLE.EVENT_ORGANISER, ROUTES.ORGANISER_HOME],
    [ROLE.EVENT_COORDINATOR, ROUTES.STAFF_HOME],
    [ROLE.EVENT_COORDINATOR_LEAD, ROUTES.STAFF_HOME],
    [ROLE.VENUE_STAFF, ROUTES.STAFF_HOME],
    [ROLE.TECHNICAL_SUPPORT_STAFF, ROUTES.STAFF_HOME],
  ])('%s lands on %s', (role, route) => {
    expect(homeFor(role)).toBe(route)
  })
})

describe('destinationAfterSignIn', () => {
  it('returns to the page the user came from', () => {
    expect(destinationAfterSignIn(ROLE.ATTENDEE, '/events?page=2')).toBe('/events?page=2')
  })

  it.each([
    ['nothing', null],
    ['an empty value', ''],
    ['another site', 'https://evil.example'],
    ['a protocol-relative address', '//evil.example'],
    ['a backslash address browsers read as another site', '/\\evil.example'],
    ['a relative path without a slash', 'events'],
  ])('ignores %s and goes to the role home', (_label, next) => {
    expect(destinationAfterSignIn(ROLE.EVENT_ORGANISER, next)).toBe(ROUTES.ORGANISER_HOME)
  })
})
