import type { ChangeRequest } from '@/features/eventRequests/api'

import { errorResponse } from '../responses'

/**
 * Each event's change requests as they stand, oldest first (SCRUM-56, ADR-0126): what the
 * change request routes keep (changeRequests.ts) and the event's record shows
 * (eventRequests.ts). Kept apart from both, so neither imports the other. None to start with.
 */

let storedChangeRequests: Record<string, ChangeRequest[]> = {}
let lastId = 0

/** Forget every change request. Runs after every test. */
export function resetMockChangeRequests(): void {
  storedChangeRequests = {}
  lastId = 0
}

/** The event's change requests, oldest first. */
export function changeRequestsOf(reference: string): ChangeRequest[] {
  return storedChangeRequests[reference] ?? []
}

/** Keep a new change request on the event, with the next id; answers it as kept. */
export function addChangeRequest(
  reference: string,
  changeRequest: Omit<ChangeRequest, 'id'>,
): ChangeRequest {
  lastId += 1
  const kept = { ...changeRequest, id: lastId }
  storedChangeRequests[reference] = [...changeRequestsOf(reference), kept]
  return kept
}

const PENDING_MESSAGE =
  'The organiser has a change request waiting for your decision. Decide the change request first.'

/**
 * SCRUM-57 AC9: the refusal of the event's own decision (approving or rejecting it, rejecting it
 * during planning, confirming it) while it has a Pending change request, or null when it has none.
 */
export function pendingChangeRequestRefusal(reference: string) {
  const isPending = changeRequestsOf(reference).some((each) => each.status === 'pending')
  if (!isPending) {
    return null
  }
  return errorResponse(409, 'change_request_pending', PENDING_MESSAGE)
}

/** Put `changed` in place of the event's request with its id. */
export function replaceChangeRequest(reference: string, changed: ChangeRequest): void {
  storedChangeRequests[reference] = changeRequestsOf(reference).map((changeRequest) =>
    changeRequest.id === changed.id ? changed : changeRequest,
  )
}
