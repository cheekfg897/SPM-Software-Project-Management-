import type { CoordinatorContact } from '../api'

/** The event's coordinator by name and email, or that none is assigned yet (SCRUM-30 AC3). */
export function CoordinatorDetails({ coordinator }: { coordinator: CoordinatorContact | null }) {
  if (coordinator === null) {
    return <p className="text-ink-muted">No coordinator is assigned yet.</p>
  }
  return (
    <p className="text-ink">
      {coordinator.full_name}
      <span className="text-ink-faint"> · </span>
      <a
        href={`mailto:${coordinator.email}`}
        className="text-flare hover:text-corona underline-offset-4 hover:underline"
      >
        {coordinator.email}
      </a>
    </p>
  )
}
