import { server } from '@/mocks/server'

/**
 * Every request the app sends to the mock backend from now until the test ends, in order.
 * Each is a clone, so a test can read its body. Recording stops after each test (setup.ts).
 */
export function recordRequests(): Request[] {
  const requests: Request[] = []
  server.events.on('request:start', ({ request }) => requests.push(request.clone()))
  return requests
}
