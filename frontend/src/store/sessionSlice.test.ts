import { ROLE } from '@/config/roles'

import {
  selectIsSignedIn,
  selectSessionUser,
  sessionReducer,
  signedIn,
  signedOut,
} from './sessionSlice'
import type { SessionState } from './sessionSlice'

const SIGNED_OUT: SessionState = { accessToken: null, user: null }
const ALICE = { id: 7, full_name: 'Alice Tan', role: ROLE.ATTENDEE }

function asRoot(session: SessionState) {
  return { session }
}

describe('sessionSlice', () => {
  it('stores the token and user when signed in', () => {
    const state = sessionReducer(SIGNED_OUT, signedIn({ accessToken: 'abc', user: ALICE }))

    expect(state).toEqual({ accessToken: 'abc', user: ALICE })
    expect(selectIsSignedIn(asRoot(state))).toBe(true)
    expect(selectSessionUser(asRoot(state))).toEqual(ALICE)
  })

  it('forgets both when signed out', () => {
    const state = sessionReducer({ accessToken: 'abc', user: ALICE }, signedOut())

    expect(state).toEqual(SIGNED_OUT)
    expect(selectIsSignedIn(asRoot(state))).toBe(false)
    expect(selectSessionUser(asRoot(state))).toBeNull()
  })
})
