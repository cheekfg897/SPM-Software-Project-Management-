import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Pagination } from './Pagination'

describe('Pagination', () => {
  it('shows where you are and moves either way', async () => {
    const onPageChange = vi.fn()
    render(<Pagination page={2} totalPages={3} onPageChange={onPageChange} />)

    expect(screen.getByRole('navigation', { name: 'Pagination' })).toHaveTextContent('Page 2 of 3')
    await userEvent.click(screen.getByRole('button', { name: 'Previous page' }))
    await userEvent.click(screen.getByRole('button', { name: 'Next page' }))

    expect(onPageChange.mock.calls).toEqual([[1], [3]])
  })

  it('cannot go before the first page or past the last', () => {
    const { rerender } = render(<Pagination page={1} totalPages={3} onPageChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()

    rerender(<Pagination page={3} totalPages={3} onPageChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
  })

  it('shows nothing when everything fits on one page', () => {
    const { container } = render(<Pagination page={1} totalPages={1} onPageChange={vi.fn()} />)

    expect(container).toBeEmptyDOMElement()
  })
})
