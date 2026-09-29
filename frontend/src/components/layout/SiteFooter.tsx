import { Link } from 'react-router'

import { ROUTES } from '@/config/routes'

export function SiteFooter() {
  return (
    <footer className="border-line/60 border-t">
      <div className="text-ink-faint mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-sm sm:flex-row sm:justify-between sm:px-6">
        <p>ConnectSphere: where organisers and attendees meet.</p>
        <p>
          ConnectSphere staff?{' '}
          <Link to={ROUTES.STAFF_LOGIN} className="text-ink-muted hover:text-ink underline">
            Staff log in
          </Link>
        </p>
      </div>
    </footer>
  )
}
