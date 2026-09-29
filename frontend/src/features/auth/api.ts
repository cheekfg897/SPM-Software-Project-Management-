import type { Role } from '@/config/roles'
import { apiRequest } from '@/lib/api'
import type { SessionUser } from '@/store'

const AUTH_PATHS = {
  LOGIN: '/api/auth/login',
  ME: '/api/auth/me',
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

export function fetchCurrentUser(): Promise<CurrentUser> {
  return apiRequest<CurrentUser>(AUTH_PATHS.ME)
}
