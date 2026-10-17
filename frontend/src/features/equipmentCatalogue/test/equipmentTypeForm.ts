import { screen } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'

/** The equipment type form's fields, by their labels. */
export const FIELD = {
  NAME: 'Name',
  DESCRIPTION: 'Description',
  TOTAL: 'Total quantity held',
  VENUE: 'Venue number',
  STORE: 'Store name',
} as const

type FieldLabel = (typeof FIELD)[keyof typeof FIELD]

/** Clear each field given and type its new value; '' leaves it empty. */
export async function fillIn(user: UserEvent, values: Partial<Record<FieldLabel, string>>) {
  for (const [label, value] of Object.entries(values)) {
    const field = await screen.findByLabelText(label)
    await user.clear(field)
    if (value !== '') {
      await user.type(field, value)
    }
  }
}

/** The JSON body of the one request sent with `method`. */
export async function bodySent(requests: Request[], method: string): Promise<unknown> {
  const sent = requests.filter((request) => request.method === method)
  expect(sent).toHaveLength(1)
  return sent[0]?.json()
}
