/**
 * SCRUM-52: the catalogue against the real backend. The endpoint doesn't exist yet
 * (docs/adr/0032-event-catalogue-contract.md), so each check waits here as a todo and becomes
 * a real test when the backend story lands. Until then the mock handlers stand in for it.
 */
describe('SCRUM-52 event catalogue contract (ADR-0032)', () => {
  it.todo('lists only confirmed events with registration enabled, soonest first, without a token')
  it.todo('pages with page, page_size, total and total_pages, and a default page size of 12')
  it.todo('answers a page past the last one with no items and the real totals')
  it.todo('searches name, description and venue name with q, ignoring case')
  it.todo('resolves when=today, this_week and this_weekend in business time')
  it.todo('filters by starts_from and starts_to, reading a time without an offset as business time')
  it.todo('refuses a range that ends before it starts with a validation error on starts_to')
  it.todo('refuses when together with a custom range, and an unknown when')
  it.todo('sets is_registered for the signed-in attendee and false for a visitor')
  it.todo('registers an attendee (201) and counts the place in places_left')
  it.todo('refuses registering without a token (401) or as another role (403)')
  it.todo(
    'refuses a second registration (409 already_registered) and a full event (409 event_full)',
  )
  it.todo('answers 404 for an event that is not open for registration')
})
