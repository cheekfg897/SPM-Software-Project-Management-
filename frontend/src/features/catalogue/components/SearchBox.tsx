import { useEffect, useState } from 'react'

import { useCatalogueParams } from '../hooks'

/** How long typing pauses before the search is sent. */
const SEARCH_DELAY_MS = 300

function SearchIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" className="text-ink-faint size-5">
      <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.6" />
      <path d="m13.5 13.5 3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

/** Search text, sent as `q` once typing pauses. The URL holds the search; this box follows it. */
export function SearchBox() {
  const { params, search } = useCatalogueParams()
  const searchInUrl = params.q ?? ''
  const [text, setText] = useState(searchInUrl)
  const [lastSeenSearch, setLastSeenSearch] = useState(searchInUrl)

  // When the URL's search changes from outside the box (clear filters, the Back button),
  // show it. Adjusting state while rendering is React's way to follow a changing value.
  if (searchInUrl !== lastSeenSearch) {
    setLastSeenSearch(searchInUrl)
    setText(searchInUrl)
  }

  useEffect(() => {
    if (text.trim() === searchInUrl) {
      return
    }
    const timer = setTimeout(() => search(text), SEARCH_DELAY_MS)
    return () => clearTimeout(timer)
  }, [text, searchInUrl, search])

  return (
    <div className="relative">
      <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center">
        <SearchIcon />
      </span>
      <input
        type="search"
        aria-label="Search events"
        placeholder="Search by name, venue or topic"
        value={text}
        onChange={(event) => setText(event.target.value)}
        className="border-line bg-surface text-ink placeholder:text-ink-faint focus:border-flare/70 w-full rounded-2xl border py-3.5 pr-4 pl-12 focus:outline-none"
      />
    </div>
  )
}
