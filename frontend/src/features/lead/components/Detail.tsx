import type { ReactNode } from 'react'

/** One labelled value in a Lead card's details list, e.g. "Date" and "12 Nov 2026". */
export function Detail({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-ink-faint text-xs tracking-wide uppercase">{term}</dt>
      <dd className="text-ink mt-0.5">{children}</dd>
    </div>
  )
}
