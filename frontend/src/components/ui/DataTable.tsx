import type { ReactNode } from 'react'

export interface DataTableColumn<Row> {
  header: string
  /** What to show in this column for one row: text, or a control. */
  cell: (row: Row) => ReactNode
}

interface DataTableProps<Row> {
  /** Names the table for screen readers; it is not drawn. */
  caption: string
  columns: DataTableColumn<Row>[]
  rows: Row[]
  getRowKey: (row: Row) => string | number
}

/** A table that scrolls sideways inside its own box on a narrow screen. */
export function DataTable<Row>({ caption, columns, rows, getRowKey }: DataTableProps<Row>) {
  return (
    <div className="border-line overflow-x-auto rounded-xl border">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-surface-raised text-ink-muted">
          <tr>
            {columns.map((column) => (
              <th key={column.header} scope="col" className="px-4 py-3 font-medium">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-line divide-y">
          {rows.map((row) => (
            <tr key={getRowKey(row)}>
              {columns.map((column) => (
                <td key={column.header} className="px-4 py-3 align-top">
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
