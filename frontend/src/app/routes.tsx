import type { RouteObject } from 'react-router'

import { SiteLayout } from '@/components/layout'
import {
  EQUIPMENT_READER_ROLES,
  INTERNAL_ROLES,
  ROLE,
  STAFF_RECORD_READER_ROLES,
} from '@/config/roles'
import type { Role } from '@/config/roles'
import { ROUTES } from '@/config/routes'
import { RequireRole } from '@/features/auth/components/RequireRole'
import { SignedOutOnly } from '@/features/auth/components/SignedOutOnly'
import { LoginPage } from '@/features/auth/pages/LoginPage'
import { OrganiserHomePage } from '@/features/auth/pages/OrganiserHomePage'
import { SignUpPage } from '@/features/auth/pages/SignUpPage'
import { StaffHomePage } from '@/features/auth/pages/StaffHomePage'
import { StaffLoginPage } from '@/features/auth/pages/StaffLoginPage'
import { BookingDecisionsPage } from '@/features/booking/pages/BookingDecisionsPage'
import { VenueRequestsPage } from '@/features/booking/pages/VenueRequestsPage'
import { CataloguePage } from '@/features/catalogue/pages/CataloguePage'
import { MyEventsPage } from '@/features/catalogue/pages/MyEventsPage'
import { EventEquipmentPage } from '@/features/equipment/pages/EventEquipmentPage'
import { AssignedEventRequests } from '@/features/eventRequests/components/AssignedEventRequests'
import { MyEventRequests } from '@/features/eventRequests/components/MyEventRequests'
import { EditDraftPage } from '@/features/eventRequests/pages/EditDraftPage'
import { EditEventPage } from '@/features/eventRequests/pages/EditEventPage'
import { EventRequestPage } from '@/features/eventRequests/pages/EventRequestPage'
import { NewEventRequestPage } from '@/features/eventRequests/pages/NewEventRequestPage'
import { StaffEventPage } from '@/features/eventRequests/pages/StaffEventPage'
import { LandingPage } from '@/features/landing/pages/LandingPage'
import { NotificationsPage } from '@/features/notifications/pages/NotificationsPage'
import { UnassignedQueuePage } from '@/features/lead/pages/UnassignedQueuePage'
import { SafetyReviewPage } from '@/features/safety/pages/SafetyReviewPage'
import { VenueSearchPage } from '@/features/venueSearch/pages/VenueSearchPage'
import { EquipmentEventRequests } from '@/features/eventRequests/components/EquipmentEventRequests'
import { VenueBookingEventRequests } from '@/features/eventRequests/components/VenueBookingEventRequests'
import { EquipmentQueue } from '@/features/techSupport/components/EquipmentQueue'
import { OversightPage } from '@/features/lead/pages/OversightPage'
import { OrganisationsPage } from '@/features/organisations/pages/OrganisationsPage'
import { EQUIPMENT_CATALOGUE_EDITOR_ROLES } from '@/features/equipmentCatalogue/constants'
import { EditEquipmentTypePage } from '@/features/equipmentCatalogue/pages/EditEquipmentTypePage'
import { EquipmentCataloguePage } from '@/features/equipmentCatalogue/pages/EquipmentCataloguePage'
import { EquipmentTypePage } from '@/features/equipmentCatalogue/pages/EquipmentTypePage'
import { NewEquipmentTypePage } from '@/features/equipmentCatalogue/pages/NewEquipmentTypePage'
import { EditVenuePage } from '@/features/venues/pages/EditVenuePage'
import { NewVenuePage } from '@/features/venues/pages/NewVenuePage'
import { VenuePage } from '@/features/venues/pages/VenuePage'
import { VenuesPage } from '@/features/venues/pages/VenuesPage'

import { EventPageForRole } from './EventPageForRole'
import { NotFoundPage } from './NotFoundPage'

const ORGANISER_ROLES: readonly Role[] = [ROLE.EVENT_ORGANISER]
const COORDINATOR_ROLES: readonly Role[] = [ROLE.EVENT_COORDINATOR]
const VENUE_STAFF_ROLES: readonly Role[] = [ROLE.VENUE_STAFF]
const LEAD_ROLES: readonly Role[] = [ROLE.EVENT_COORDINATOR_LEAD]
const ATTENDEE_ROLES: readonly Role[] = [ROLE.ATTENDEE]
const SAFETY_OFFICER_ROLES: readonly Role[] = [ROLE.SAFETY_OFFICER]

/** The page tree. The browser router (App) and the test router (renderApp) both use it. */
export const appRoutes: RouteObject[] = [
  {
    element: <SiteLayout />,
    children: [
      {
        // The front page is for visitors; someone signed in is taken to their role's home (SCRUM-6).
        path: ROUTES.HOME,
        element: (
          <SignedOutOnly>
            <LandingPage />
          </SignedOutOnly>
        ),
      },
      { path: ROUTES.EVENTS, element: <CataloguePage /> },
      {
        path: ROUTES.MY_EVENTS,
        element: (
          <RequireRole allowedRoles={ATTENDEE_ROLES} loginRoute={ROUTES.LOGIN}>
            <MyEventsPage />
          </RequireRole>
        ),
      },
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
        path: ROUTES.NEW_EVENT_REQUEST,
        element: (
          <RequireRole allowedRoles={ORGANISER_ROLES} loginRoute={ROUTES.LOGIN}>
            <NewEventRequestPage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.EDIT_DRAFT,
        element: (
          <RequireRole allowedRoles={ORGANISER_ROLES} loginRoute={ROUTES.LOGIN}>
            <EditDraftPage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.ORGANISER_REQUEST,
        element: (
          <RequireRole allowedRoles={ORGANISER_ROLES} loginRoute={ROUTES.LOGIN}>
            <EventRequestPage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.STAFF_HOME,
        element: (
          <RequireRole allowedRoles={INTERNAL_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <StaffHomePage>
              <AssignedEventRequests />
              <EquipmentQueue />
              <EquipmentEventRequests />
              <VenueBookingEventRequests />
            </StaffHomePage>
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
        path: ROUTES.BOOKING_DECISIONS,
        element: (
          <RequireRole allowedRoles={VENUE_STAFF_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <BookingDecisionsPage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.COORDINATOR_EVENT,
        element: (
          <EventPageForRole>
            <RequireRole allowedRoles={COORDINATOR_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
              <EventRequestPage />
            </RequireRole>
          </EventPageForRole>
        ),
      },
      {
        path: ROUTES.EDIT_EVENT,
        element: (
          <RequireRole allowedRoles={COORDINATOR_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <EditEventPage />
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
      {
        path: ROUTES.STAFF_EVENT,
        element: (
          <RequireRole allowedRoles={STAFF_RECORD_READER_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <StaffEventPage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.LEAD_QUEUE,
        element: (
          <RequireRole allowedRoles={LEAD_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <UnassignedQueuePage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.SAFETY_REVIEW,
        element: (
          <RequireRole allowedRoles={SAFETY_OFFICER_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <SafetyReviewPage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.VENUE_SEARCH,
        element: (
          <RequireRole allowedRoles={COORDINATOR_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <VenueSearchPage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.LEAD_OVERSIGHT,
        element: (
          <RequireRole allowedRoles={LEAD_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <OversightPage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.ORGANISATIONS,
        element: (
          <RequireRole allowedRoles={INTERNAL_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <OrganisationsPage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.EQUIPMENT_CATALOGUE,
        element: (
          <RequireRole allowedRoles={INTERNAL_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <EquipmentCataloguePage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.EQUIPMENT_TYPE,
        element: (
          <RequireRole allowedRoles={INTERNAL_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <EquipmentTypePage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.NEW_EQUIPMENT_TYPE,
        element: (
          <RequireRole
            allowedRoles={EQUIPMENT_CATALOGUE_EDITOR_ROLES}
            loginRoute={ROUTES.STAFF_LOGIN}
          >
            <NewEquipmentTypePage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.EDIT_EQUIPMENT_TYPE,
        element: (
          <RequireRole
            allowedRoles={EQUIPMENT_CATALOGUE_EDITOR_ROLES}
            loginRoute={ROUTES.STAFF_LOGIN}
          >
            <EditEquipmentTypePage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.VENUES,
        element: (
          <RequireRole allowedRoles={INTERNAL_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <VenuesPage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.VENUE,
        element: (
          <RequireRole allowedRoles={INTERNAL_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <VenuePage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.NEW_VENUE,
        element: (
          <RequireRole allowedRoles={VENUE_STAFF_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <NewVenuePage />
          </RequireRole>
        ),
      },
      {
        path: ROUTES.EDIT_VENUE,
        element: (
          <RequireRole allowedRoles={VENUE_STAFF_ROLES} loginRoute={ROUTES.STAFF_LOGIN}>
            <EditVenuePage />
          </RequireRole>
        ),
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
