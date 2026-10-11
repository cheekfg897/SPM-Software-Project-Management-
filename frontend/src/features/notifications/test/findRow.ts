import { screen } from '@testing-library/react'

/** The list item that holds `message`, once it has rendered. */
export async function findRow(message: string): Promise<HTMLElement> {
  const row = (await screen.findByText(message)).closest('li')
  if (row === null) {
    throw new Error(`"${message}" is not in a list item`)
  }
  return row
}
