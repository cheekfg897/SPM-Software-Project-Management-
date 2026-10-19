import {
  editDraftPath,
  eventEquipmentPath,
  loginPathReturningTo,
  replacementRequestPath,
  ROUTES,
} from './routes'

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

describe('editDraftPath', () => {
  it("builds the page for editing one of the organiser's drafts", () => {
    expect(editDraftPath('EVR-3HD8PL2W')).toBe('/organiser/requests/EVR-3HD8PL2W/edit')
  })

  it('escapes characters that would change the path', () => {
    expect(editDraftPath('a/b')).toBe('/organiser/requests/a%2Fb/edit')
  })
})

describe('SCRUM-92 replacementRequestPath', () => {
  it('opens the event’s venue requests to replace the flagged arrangement with the venue chosen', () => {
    expect(replacementRequestPath('EVR-BOOK0107', 9104, 2)).toBe(
      '/events/EVR-BOOK0107/venue-requests?replaces=9104&venue=2',
    )
  })
})
