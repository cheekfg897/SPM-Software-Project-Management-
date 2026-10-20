import type { RequestHandler } from 'msw'

import { authHandlers, resetMockAccounts } from './auth'
import { bookingHandlers, resetMockBooking } from './booking'
import { catalogueHandlers, resetMockCatalogue } from './catalogue'
import { eventRequestHandlers, resetMockEventRequests } from './eventRequests'
import { eventEditHandlers, resetMockEventEdits } from './eventEdits'
import { eventRecordSectionHandlers, resetMockEventHistory } from './eventRecordSections'
import { notificationHandlers, resetMockNotifications } from './notifications'
import { equipmentHandlers, resetMockEquipment } from './equipment'
import { equipmentOutOfServiceHandlers } from './equipmentOutOfService'
import { leadHandlers, resetMockLeadQueue } from './lead'
import { resetMockSafety, safetyHandlers } from './safety'
import { venueSearchHandlers } from './venueSearch'
import { techSupportHandlers } from './techSupport'
import { organisationHandlers, resetMockOrganisations } from './organisations'
import { equipmentCatalogueHandlers, resetMockEquipmentCatalogue } from './equipmentCatalogue'
import { resetMockVenues, venueHandlers } from './venues'
import { eventPlanningHandlers } from './eventPlanning'

/**
 * Every mock handler, one file per feature. They stand in for the backend in unit tests,
 * in Playwright runs and in `npm run dev:mock`. They follow the backend's real response
 * shapes; the integration tests in src/integration check those shapes against the backend.
 */
export const handlers: RequestHandler[] = [
  ...authHandlers,
  ...catalogueHandlers,
  ...eventRequestHandlers,
  ...eventRecordSectionHandlers,
  ...eventEditHandlers,
  ...notificationHandlers,
  ...bookingHandlers,
  ...equipmentHandlers,
  ...equipmentOutOfServiceHandlers,
  ...leadHandlers,
  ...safetyHandlers,
  ...venueSearchHandlers,
  ...equipmentCatalogueHandlers,
  ...techSupportHandlers,
  ...organisationHandlers,
  ...venueHandlers,
  ...eventPlanningHandlers,
]

/** Put the mock backend's data back as it started, so no test sees another's sign-ups, registrations or requests. */
export function resetMockBackend(): void {
  resetMockAccounts()
  resetMockCatalogue()
  resetMockEventRequests()
  resetMockEventHistory()
  resetMockEventEdits()
  resetMockNotifications()
  resetMockBooking()
  resetMockEquipment()
  resetMockLeadQueue()
  resetMockSafety()
  resetMockOrganisations()
  resetMockEquipmentCatalogue()
  resetMockVenues()
}
