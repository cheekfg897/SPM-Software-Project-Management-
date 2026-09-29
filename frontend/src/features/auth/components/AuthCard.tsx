import type { ReactNode } from 'react'

interface AuthCardProps {
  title: string
  description: string
  children: ReactNode
  /** Links under the form, e.g. to sign up instead. */
  footer?: ReactNode
}

/** The frame for the log-in and sign-up pages: a card glowing like the disk behind it. */
export function AuthCard({ title, description, children, footer }: AuthCardProps) {
  return (
    <main className="relative flex min-h-dvh items-center justify-center overflow-hidden px-4 pt-28 pb-20">
      <div
        aria-hidden="true"
        className="from-flare/35 via-nebula/20 pointer-events-none absolute top-1/3 left-1/2 size-[40rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-radial to-transparent to-70% blur-3xl"
      />
      <section className="border-line bg-surface/90 shadow-void relative w-full max-w-md rounded-3xl border p-7 shadow-2xl backdrop-blur-sm sm:p-10">
        <h1 className="font-display text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="text-ink-muted mt-2">{description}</p>
        <div className="mt-8">{children}</div>
        {footer !== undefined && (
          <div className="border-line text-ink-muted mt-8 border-t pt-6 text-sm">{footer}</div>
        )}
      </section>
    </main>
  )
}
