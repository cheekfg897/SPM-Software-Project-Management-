import type { renderApp } from '@/test/render'

type AppView = ReturnType<typeof renderApp>

/** The search's endpoint, to pick its requests out or answer it differently in one test. */
export const SEARCH_URL = '/api/venues/search'

/** The searches among the recorded requests, in the order they were sent. */
export function searchesSent(requests: Request[]): Request[] {
  return requests.filter((request) => new URL(request.url).pathname === SEARCH_URL)
}

/** Type into a field from scratch, replacing whatever it held. */
export async function typeInto(view: AppView, label: string, text: string) {
  const field = await view.findByLabelText(label)
  await view.user.clear(field)
  await view.user.type(field, text)
}

/** Fill the four filters the form requires, then any others. */
export async function fill(view: AppView, others: Record<string, string> = {}) {
  await typeInto(view, 'Date', '2026-11-20')
  await typeInto(view, 'Start time', '09:00')
  await typeInto(view, 'End time', '17:00')
  await typeInto(view, 'Minimum capacity', '120')
  for (const [label, text] of Object.entries(others)) {
    await typeInto(view, label, text)
  }
}

/** Fill the form as `fill` does, then search. */
export async function search(view: AppView, others: Record<string, string> = {}) {
  await fill(view, others)
  await view.user.click(view.getByRole('button', { name: 'Search venues' }))
}
