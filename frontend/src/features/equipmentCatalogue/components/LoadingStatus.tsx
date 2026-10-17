import { Spinner } from '@/components/ui'

/** Says what is loading, next to a spinner. */
export function LoadingStatus({ what }: { what: string }) {
  return (
    <p role="status" className="text-ink-muted flex items-center gap-2">
      <Spinner /> Loading {what}…
    </p>
  )
}
