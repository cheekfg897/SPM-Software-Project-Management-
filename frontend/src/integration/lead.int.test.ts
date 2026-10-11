/**
 * SCRUM-95: the Lead's queue against the real backend. Staff accounts can only be made with
 * `flask create-staff-user` (ADR-0023), and the queue needs submitted requests, so these checks
 * wait here as todos until the integration setup can seed both. Until then the mock handlers in
 * src/mocks/handlers/lead.ts stand in for the backend and these todos name what must be pinned.
 */
describe('SCRUM-95 Lead queue contract (ADR-0036)', () => {
  it.todo('lists each queued request with exactly reference and the six AC2 fields, oldest first')
  it.todo('answers an empty queue with an empty list and the "waiting to be assigned" message')
  it.todo('refuses the queue to an Event Coordinator (403) and to a visitor (401)')
  it.todo('assigns by coordinator_email and answers the request with its coordinator')
  it.todo('takes an assigned request out of the queue')
  it.todo('answers 404 for an unknown reference and 409 for one that already has a coordinator')
  it.todo('answers 400 on coordinator_email for an unknown or non-coordinator email, checked last')
})
