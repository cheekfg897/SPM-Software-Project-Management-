import { screen, within } from '@testing-library/react'
import type userEvent from '@testing-library/user-event'

type User = ReturnType<typeof userEvent.setup>

/** One opening period's controls, found by the group its legend names ("Period 2"). */
export function period(number: number) {
  return within(screen.getByRole('group', { name: `Period ${number}` }))
}

/** How many opening periods the form holds. */
export function periodCount(): number {
  return screen.queryAllByRole('group', { name: /^Period \d+$/ }).length
}

/** Empty a text control and type `text` into it, as a person changing a value would. */
export async function retype(user: User, control: HTMLElement, text: string) {
  await user.clear(control)
  if (text !== '') {
    await user.type(control, text)
  }
}

/** The JSON body of the first request sent with `method`. */
export async function bodyOf(requests: Request[], method: string): Promise<unknown> {
  const sent = requests.find((request) => request.method === method)
  if (sent === undefined) {
    throw new Error(`No ${method} request was sent.`)
  }
  return sent.json()
}
