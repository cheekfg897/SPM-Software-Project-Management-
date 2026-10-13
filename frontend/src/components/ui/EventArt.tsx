/** Decorative artwork, one of these picked by the seed so an event always looks the same. */
const ART_GRADIENTS = [
  'from-corona via-flare to-ember',
  'from-flare via-ember to-nebula',
  'from-nebula via-ember to-flare',
  'from-corona via-nebula to-void',
] as const

/** A small black hole: a glowing ring around a dark core. Hidden from screen readers. */
export function EventArt({ seed }: { seed: number }) {
  const gradient = ART_GRADIENTS[seed % ART_GRADIENTS.length]
  return (
    <div
      aria-hidden="true"
      className={`relative hidden size-24 shrink-0 overflow-hidden rounded-xl bg-gradient-to-br sm:block ${gradient}`}
    >
      <div className="bg-void absolute inset-[22%] rounded-full shadow-[0_0_18px_6px_rgb(6_5_11/0.6)]" />
    </div>
  )
}
