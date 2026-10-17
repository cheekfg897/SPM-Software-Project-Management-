import type { renderApp } from '@/test/render'

type AppView = ReturnType<typeof renderApp>

/** Type into a field from scratch: after a form reset, user-event still remembers the old text. */
export async function typeInto(view: AppView, label: string, text: string) {
  const field = await view.findByLabelText(label)
  await view.user.clear(field)
  await view.user.type(field, text)
}

/** Fill the venue request form's required fields; the venue is the one id the form needs. */
export async function fillRequest(view: AppView, venueId: number) {
  await typeInto(view, 'Venue ID', String(venueId))
  await typeInto(view, 'Starts', '2026-11-10T09:00')
  await typeInto(view, 'Ends', '2026-11-10T12:00')
  await typeInto(view, 'Purpose', 'Keynote')
}
