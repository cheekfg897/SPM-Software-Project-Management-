/**
 * The client organisations the mock starts with (SCRUM-66). Their ids are the ones mock sign-up
 * accepts (MOCK_ORGANISATION_IDS); organisation 1 is the mock organiser's. They are saved out of
 * name order, so the list's order (by name) is visible.
 *
 * No imports: the Playwright tests read this file, and they don't know the `@/` alias.
 */
export const MOCK_ORGANISATIONS = [
  {
    id: 1,
    name: 'Orchid Events Co',
    contact_name: 'Priya Nair',
    contact_email: 'priya@orchidevents.test',
    contact_phone: '+65 6123 4567',
    created_at: '2026-09-25T10:00:00+00:00',
  },
  {
    id: 2,
    name: 'Harbour Lights Ltd',
    contact_name: 'Marcus Lee',
    contact_email: 'marcus@harbourlights.test',
    contact_phone: null,
    created_at: '2026-09-26T10:00:00+00:00',
  },
  {
    id: 3,
    name: 'Acme Conferences',
    contact_name: 'Siti Rahman',
    contact_email: 'siti@acmeconf.test',
    contact_phone: '6234-5678',
    created_at: '2026-09-27T10:00:00+00:00',
  },
] as const
