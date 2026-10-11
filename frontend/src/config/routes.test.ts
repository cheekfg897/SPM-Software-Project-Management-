import { eventEquipmentPath, loginPathReturningTo, ROUTES } from './routes'

describe('loginPathReturningTo', () => {
  it('sends the visitor to log in, remembering the page to come back to', () => {
    expect(loginPathReturningTo('/events?page=2')).toBe('/login?next=%2Fevents%3Fpage%3D2')
  })

  it('can send staff to their own log-in page', () => {
    expect(loginPathReturningTo(ROUTES.STAFF_HOME, ROUTES.STAFF_LOGIN)).toBe(
      '/staff/login?next=%2Fstaff',
    )
  })
})

describe('eventEquipmentPath', () => {
  it('builds the equipment page path for an event reference', () => {
    expect(eventEquipmentPath('EVR-AB12')).toBe('/events/EVR-AB12/equipment')
  })

  it('escapes characters that would change the path', () => {
    expect(eventEquipmentPath('a/b')).toBe('/events/a%2Fb/equipment')
  })
})
