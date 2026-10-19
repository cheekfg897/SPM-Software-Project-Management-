import { within } from '@testing-library/react'

/** Each term in `container` with its definition, as the page shows them: { Damaged: '2' }. */
export function definitionsIn(container: HTMLElement): Record<string, string | null> {
  const terms = within(container)
    .getAllByRole('term')
    .map((term) => term.textContent)
  const values = within(container)
    .getAllByRole('definition')
    .map((value) => value.textContent)
  return Object.fromEntries(terms.map((term, index) => [term, values[index] ?? null]))
}
