import { Button, EmptyState, ErrorAlert, Pagination } from '@/components/ui'
import { ApiError } from '@/lib/api'

import { useCatalogue, useCatalogueParams } from '../hooks'
import { hasFilters } from '../searchParams'

import { DayTimeline } from './DayTimeline'
import { EventCard } from './EventCard'

const SKELETON_CARDS = 3

function countLabel(total: number): string {
  return total === 1 ? '1 event' : `${total} events`
}

function CatalogueSkeleton() {
  return (
    <div role="status" className="space-y-4">
      <span className="sr-only">Loading events…</span>
      {Array.from({ length: SKELETON_CARDS }, (_, index) => (
        <div
          key={index}
          aria-hidden="true"
          className="border-line/50 bg-surface/60 h-36 animate-pulse rounded-2xl border md:ml-[10rem]"
        />
      ))}
    </div>
  )
}

/** The page of events the backend returned, or why there isn't one. */
export function CatalogueResults() {
  const { params, goToPage, clearFilters } = useCatalogueParams()
  const catalogue = useCatalogue(params)

  if (catalogue.isPending) {
    return <CatalogueSkeleton />
  }

  if (catalogue.isError) {
    // Asking again only helps when the backend didn't refuse the request itself.
    const canRetry = !(catalogue.error instanceof ApiError && catalogue.error.isClientError)
    return (
      <div className="space-y-4">
        <ErrorAlert error={catalogue.error} />
        {canRetry && (
          <Button variant="secondary" onClick={() => void catalogue.refetch()}>
            Try again
          </Button>
        )}
      </div>
    )
  }

  const { data } = catalogue
  if (data.items.length === 0) {
    return hasFilters(params) ? (
      <EmptyState message="No events match your filters.">
        <Button variant="secondary" className="mt-6" onClick={clearFilters}>
          Clear filters
        </Button>
      </EmptyState>
    ) : (
      <EmptyState message="No events are open for registration yet." />
    )
  }

  function changePage(page: number) {
    goToPage(page)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <section
      aria-label="Results"
      aria-busy={catalogue.isPlaceholderData}
      className={`space-y-8 transition-opacity ${catalogue.isPlaceholderData ? 'opacity-60' : ''}`}
    >
      <p className="text-ink-muted text-sm">{countLabel(data.total)}</p>
      <DayTimeline
        events={data.items}
        keyOf={(event) => event.id}
        renderEvent={(event) => <EventCard event={event} />}
      />
      <Pagination page={data.page} totalPages={data.total_pages} onPageChange={changePage} />
    </section>
  )
}
