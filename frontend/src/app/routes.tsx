import type { RouteObject } from 'react-router'

import { SiteLayout } from '@/components/layout'
import { ROUTES } from '@/config/routes'
import { LoginPage } from '@/features/auth/pages/LoginPage'
import { OrganiserHomePage } from '@/features/auth/pages/OrganiserHomePage'
import { SignUpPage } from '@/features/auth/pages/SignUpPage'
import { StaffHomePage } from '@/features/auth/pages/StaffHomePage'
import { StaffLoginPage } from '@/features/auth/pages/StaffLoginPage'
import { CataloguePage } from '@/features/catalogue/pages/CataloguePage'
import { LandingPage } from '@/features/landing/pages/LandingPage'

import { NotFoundPage } from './NotFoundPage'

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
      { path: ROUTES.ORGANISER_HOME, element: <OrganiserHomePage /> },
      { path: ROUTES.STAFF_HOME, element: <StaffHomePage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
