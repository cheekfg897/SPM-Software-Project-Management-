interface SectionHeadingProps {
  id: string
  eyebrow: string
  title: string
  description?: string
}

/** The small label, big title and optional line of text that open each landing section. */
export function SectionHeading({ id, eyebrow, title, description }: SectionHeadingProps) {
  return (
    <div>
      <p className="text-flare text-xs font-semibold tracking-[0.25em] uppercase">{eyebrow}</p>
      <h2
        id={id}
        className="font-display mt-3 text-3xl font-semibold tracking-tight text-balance sm:text-5xl"
      >
        {title}
      </h2>
      {description !== undefined && (
        <p className="text-ink-muted mt-4 max-w-md text-pretty">{description}</p>
      )}
    </div>
  )
}
