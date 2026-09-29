/** Every page's path. Link to pages through these, never with a typed-out string. */
export const ROUTES = {
  HOME: '/',
  EVENTS: '/events',
  LOGIN: '/login',
  SIGN_UP: '/signup',
  STAFF_LOGIN: '/staff/login',
  ORGANISER_HOME: '/organiser',
  STAFF_HOME: '/staff',
} as const

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES]
