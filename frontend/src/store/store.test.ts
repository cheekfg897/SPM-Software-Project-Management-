import { http, HttpResponse } from 'msw'

import { ROLE } from '@/config/roles'
import { apiRequest } from '@/lib/api'
import { server } from '@/mocks/server'

import { loadSession } from './persistedSession'
import { signedIn } from './sessionSlice'
import { createAppStore } from './store'

const SESSION = { accessToken: 'abc', user: { id: 1, full_name: 'Bo', role: ROLE.ATTENDEE } }

describe('createAppStore', () => {
  it('starts from the saved session', () => {
    localStorage.setItem('connectsphere.session', JSON.stringify(SESSION))

    expect(createAppStore().getState().session).toEqual(SESSION)
  })

  it('saves the session whenever it changes', () => {
    const store = createAppStore()

    store.dispatch(signedIn(SESSION))

    expect(loadSession()).toEqual(SESSION)
  })

  it('signs out when the backend refuses the stored token', async () => {
    const store = createAppStore()
    store.dispatch(signedIn(SESSION))
    server.use(
      http.get('/api/auth/me', () =>
        HttpResponse.json({ error: 'authentication_error', message: 'Expired.' }, { status: 401 }),
      ),
    )

    await expect(apiRequest('/api/auth/me')).rejects.toThrow('Expired.')

    expect(store.getState().session.accessToken).toBeNull()
  })
})
