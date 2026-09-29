import { ROLE } from '@/config/roles'

import { loadSession, saveSession, SESSION_STORAGE_KEY } from './persistedSession'

const SESSION = { accessToken: 'abc', user: { id: 1, full_name: 'Bo', role: ROLE.VENUE_STAFF } }

describe('persistedSession', () => {
  it('reads back a saved session', () => {
    saveSession(SESSION)

    expect(loadSession()).toEqual(SESSION)
  })

  it('removes the saved session when signed out', () => {
    saveSession(SESSION)
    saveSession({ accessToken: null, user: null })

    expect(localStorage.getItem(SESSION_STORAGE_KEY)).toBeNull()
    expect(loadSession()).toEqual({ accessToken: null, user: null })
  })

  it.each([
    ['nothing saved', null],
    ['not JSON', '{oops'],
    ['a bare value', 'null'],
    ['the wrong shape', JSON.stringify({ accessToken: 5 })],
    ['a user that is not an object', JSON.stringify({ ...SESSION, user: 'Bo' })],
    ['an unknown role', JSON.stringify({ ...SESSION, user: { ...SESSION.user, role: 'admin' } })],
  ])('starts signed out when storage holds %s', (_label, stored) => {
    if (stored !== null) {
      localStorage.setItem(SESSION_STORAGE_KEY, stored)
    }

    expect(loadSession()).toEqual({ accessToken: null, user: null })
  })
})
