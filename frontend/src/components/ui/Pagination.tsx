import { Button } from './Button'

interface PaginationProps {
  /** The current page, 1-based, as the backend reported it. */
  page: number
  totalPages: number
  onPageChange: (page: number) => void
}

/** Previous and next around "Page X of Y". Shows nothing when there is only one page. */
export function Pagination({ page, totalPages, onPageChange }: PaginationProps) {
  if (totalPages <= 1) {
    return null
  }
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-4">
      <Button
        variant="secondary"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        aria-label="Previous page"
      >
        ← Previous
      </Button>
      <p className="text-ink-muted text-sm">
        Page {page} of {totalPages}
      </p>
      <Button
        variant="secondary"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        aria-label="Next page"
      >
        Next →
      </Button>
    </nav>
  )
}
