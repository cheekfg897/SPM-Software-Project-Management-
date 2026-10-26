import type { Role } from '@/config/roles'
import { apiRequest } from '@/lib/api'
import type { SessionUser } from '@/store'

const AUTH_PATHS = {
  LOGIN: '/api/auth/login',
  REGISTER: '/api/auth/register',
  ME: '/api/auth/me',
  LOGOUT: '/api/auth/logout',
} as const

export interface LoginCredentials {
  email: string
  password: string
}

/** `POST /api/auth/login` (SCRUM-6). */
export interface LoginResponse {
  access_token: string
  token_type: 'Bearer'
  user: SessionUser
}

/**
 * `POST /api/auth/register` (SCRUM-65). Only an Event Organiser sends `organisation_id`: the
 * id of the client organisation ConnectSphere staff recorded for them (ADR-0013).
 */
export interface Registration {
  full_name: string
  email: string
  password: string
  role: Role
  organisation_id?: number | null
}

/** `GET /api/auth/me`: the fields the frontend reads from the backend's user. */
export interface CurrentUser {
  id: number
  email: string
  full_name: string
  role: Role
}

export const authKeys = {
  all: ['auth'] as const,
  /** Keyed by user, so a different user never sees the last one's cached details. */
  me: (userId: number | undefined) => [...authKeys.all, 'me', userId] as const,
}

export function logIn(credentials: LoginCredentials): Promise<LoginResponse> {
  return apiRequest<LoginResponse>(AUTH_PATHS.LOGIN, { method: 'POST', body: credentials })
}

/** Create the account. The response is the new user, which sign-up doesn't need. */
export async function register(registration: Registration): Promise<void> {
  await apiRequest<unknown>(AUTH_PATHS.REGISTER, { method: 'POST', body: registration })
}

export function fetchCurrentUser(): Promise<CurrentUser> {
  return apiRequest<CurrentUser>(AUTH_PATHS.ME)
}

/**
 * `POST /api/auth/logout` (SCRUM-89): the backend revokes the token this request carries, so it
 * stops working everywhere (ADR-0110). Call it while the session still holds the token.
 */
export async function logOut(): Promise<void> {
  await apiRequest<undefined>(AUTH_PATHS.LOGOUT, { method: 'POST' })
}
