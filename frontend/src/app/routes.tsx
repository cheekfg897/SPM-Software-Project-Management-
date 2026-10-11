import type { RouteObject } from 'react-router'

import { SiteLayout } from '@/components/layout'
import { EQUIPMENT_READER_ROLES, INTERNAL_ROLES, ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { ROUTES } from '@/config/routes'
import { RequireRole } from '@/features/auth/components/RequireRole'
import { LoginPage } from '@/features/auth/pages/LoginPage'
import { OrganiserHomePage } from '@/features/auth/pages/OrganiserHomePage'
import { SignUpPage } from '@/features/auth/pages/SignUpPage'
import { StaffHomePage } from '@/features/auth/pages/StaffHomePage'
import { StaffLoginPage } from '@/features/auth/pages/StaffLoginPage'
import { VenueRequestsPage } from '@/features/booking/pages/VenueRequestsPage'
import { CataloguePage } from '@/features/catalogue/pages/CataloguePage'
import { EventEquipmentPage } from '@/features/equipment/pages/EventEquipmentPage'
import { MyEventRequests } from '@/features/eventRequests/components/MyEventRequests'
import { LandingPage } from '@/features/landing/pages/LandingPage'
import { NotificationsPage } from '@/features/notifications/pages/NotificationsPage'

import { NotFoundPage } from './NotFoundPage'

const ORGANISER_ROLES: readonly Role[] = [ROLE.EVENT_ORGANISER]
const COORDINATOR_ROLES: readonly Role[] = [ROLE.EVENT_COORDINATOR]

/** The page tree. The browser router (App) and the test router (renderApp) both use it. */
export const appRoutes: RouteObject[] = [
  {
    element: <SiteLayout />,
    children: [
      { path: ROUTES.HOME, element: <LandingPage /> },
      { path: ROUTES.EVENTS, element: <CataloguePage /> },
      { path: ROUTES.LOGIN, element: <LoginPage /> },
      { path: ROUTES.SIGN_UP, element: <SignUpPage /> },
      { path: ROUTES.STAFF_LOGIN, element: <StaffLoginPage /> },
      {
        path: ROUTES.ORGANISER_HOME,
        element: (
          <RequireRole allowedRoles={ORGANISER_ROLES} loginRoute={ROUTES.LOGIN}>
            <OrganiserHomePage>
              <MyEventRequests />
            </OrganiserHomePage>
          </RequireRole>
        ),
      },
      {
        path: ROUTES.STAFF_HOME,
        element: (
          <RequireRole allowedRoles={INTERNAL_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <StaffHomePage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.NOTIFICATIONS,
        element: (
          <RequireRole loginRoute={ROUTES.LOGIN}>
            <NotificationsPage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.VENUE_REQUESTS,
        element: (
          <RequireRole allowedRoles={COORDINATOR_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <VenueRequestsPage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.EVENT_EQUIPMENT,
        element: (
          <RequireRole allowedRoles={EQUIPMENT_READER_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <EventEquipmentPage />
          </RequireRole>
        ),
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
