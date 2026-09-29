import { Link } from 'react-router'

import { ROUTES } from '@/config/routes'

/** The mark and the name. On phones only the mark shows; the name is still the link's label. */
export function Logo() {
  return (
    <Link to={ROUTES.HOME} className="font-display flex items-center gap-2 text-lg font-semibold">
      <span
        aria-hidden="true"
        className="bg-void size-5 rounded-full shadow-[0_0_0_2px_var(--color-flare),0_0_14px_3px_var(--color-ember)]"
      />
      <span className="sr-only sm:not-sr-only">ConnectSphere</span>
    </Link>
  )
}
