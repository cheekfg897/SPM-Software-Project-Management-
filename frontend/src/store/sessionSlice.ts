import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'

import type { Role } from '@/config/roles'

/** The signed-in user, as `POST /api/auth/login` returns it. */
export interface SessionUser {
  id: number
  full_name: string
  role: Role
}

/**
 * Who is signed in. This is the only state the frontend keeps for itself; everything else
 * is read from the backend through TanStack Query.
 */
export interface SessionState {
  accessToken: string | null
  user: SessionUser | null
}

export interface SignedInPayload {
  accessToken: string
  user: SessionUser
}

const SIGNED_OUT: SessionState = { accessToken: null, user: null }

const sessionSlice = createSlice({
  name: 'session',
  initialState: SIGNED_OUT,
  reducers: {
    signedIn: (_state, action: PayloadAction<SignedInPayload>) => action.payload,
    signedOut: () => SIGNED_OUT,
  },
})

export const { signedIn, signedOut } = sessionSlice.actions
export const sessionReducer = sessionSlice.reducer

interface HasSession {
  session: SessionState
}

export function selectSessionUser(state: HasSession): SessionUser | null {
  return state.session.user
}

export function selectIsSignedIn(state: HasSession): boolean {
  return state.session.accessToken !== null
}

export function selectAccessToken(state: HasSession): string | null {
  return state.session.accessToken
}
