import { render, screen, within } from '@testing-library/react'

import { DataTable } from './DataTable'

interface Fruit {
  id: number
  name: string
  count: number
}

const FRUIT: Fruit[] = [
  { id: 1, name: 'Apple', count: 3 },
  { id: 2, name: 'Pear', count: 0 },
]

const COLUMNS = [
  { header: 'Fruit', cell: (fruit: Fruit) => fruit.name },
  { header: 'Count', cell: (fruit: Fruit) => `${fruit.count} left` },
]

describe('DataTable', () => {
  it('shows a named table with a header per column and a row per item', () => {
    render(
      <DataTable caption="Fruit stock" columns={COLUMNS} rows={FRUIT} getRowKey={(f) => f.id} />,
    )

    const table = screen.getByRole('table', { name: 'Fruit stock' })
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((cell) => cell.textContent),
    ).toEqual(['Fruit', 'Count'])
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((row) => row.textContent)).toEqual(['Apple3 left', 'Pear0 left'])
  })

  it('renders a cell as whatever its column returns, such as a control', () => {
    const columns = [
      ...COLUMNS,
      { header: 'Action', cell: (fruit: Fruit) => <button>Eat {fruit.name}</button> },
    ]
    render(
      <DataTable caption="Fruit stock" columns={columns} rows={FRUIT} getRowKey={(f) => f.id} />,
    )

    expect(screen.getByRole('button', { name: 'Eat Pear' })).toBeInTheDocument()
  })
})
