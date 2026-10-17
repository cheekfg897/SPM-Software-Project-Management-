/** A type's description, or a faint note that it has none. */
export function DescriptionText({ description }: { description: string | null }) {
  if (description === null) {
    return <span className="text-ink-faint">No description</span>
  }
  return <span className="text-ink-muted">{description}</span>
}
