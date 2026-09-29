import type { ReactNode } from 'react'

interface PageContainerProps {
  title: string
  description?: string
  children?: ReactNode
}

/** The standard page frame: space for the fixed header, a width limit, and the page's h1. */
export function PageContainer({ title, description, children }: PageContainerProps) {
  return (
    <main className="mx-auto max-w-6xl px-4 pt-28 pb-20 sm:px-6">
      <h1 className="font-display text-4xl font-semibold tracking-tight">{title}</h1>
      {description !== undefined && <p className="text-ink-muted mt-3 max-w-2xl">{description}</p>}
      {children}
    </main>
  )
}
