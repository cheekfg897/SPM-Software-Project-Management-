const NO_PLANNING_NOTES = 'No planning notes yet.'

/** The event's planning notes as the coordinator last saved them, or that there are none yet. */
export function PlanningNotes({ notes }: { notes: string | null }) {
  if (notes === null) {
    return <p className="text-ink-muted">{NO_PLANNING_NOTES}</p>
  }
  return <p className="text-ink whitespace-pre-line">{notes}</p>
}
