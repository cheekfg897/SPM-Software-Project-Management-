import { isRole } from '@/config/roles'
import { isRecord } from '@/lib/isRecord'

import type { SessionState, SessionUser } from './sessionSlice'

/** Kept in localStorage so a refresh doesn't sign the user out. */
export const SESSION_STORAGE_KEY = 'connectsphere.session'

const SIGNED_OUT: SessionState = { accessToken: null, user: null }

function isSessionUser(value: unknown): value is SessionUser {
  return (
    isRecord(value) &&
    typeof value.id === 'number' &&
    typeof value.full_name === 'string' &&
    isRole(value.role)
  )
}

function isSignedInSession(value: unknown): value is SessionState {
  return isRecord(value) && typeof value.accessToken === 'string' && isSessionUser(value.user)
}

/** The saved session, or signed out when nothing valid is saved. */
export function loadSession(): SessionState {
  const stored = localStorage.getItem(SESSION_STORAGE_KEY)
  if (stored === null) {
    return SIGNED_OUT
  }
  try {
    const parsed: unknown = JSON.parse(stored)
    return isSignedInSession(parsed) ? parsed : SIGNED_OUT
  } catch {
    return SIGNED_OUT
  }
}

export function saveSession(session: SessionState): void {
  if (session.accessToken === null) {
    localStorage.removeItem(SESSION_STORAGE_KEY)
    return
  }
  localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session))
}
