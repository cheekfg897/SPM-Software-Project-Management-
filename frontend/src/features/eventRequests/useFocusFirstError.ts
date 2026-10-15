import { useEffect } from 'react'
import type { RefObject } from 'react'

/**
 * After the backend refuses the form, move to the first field it refused, so a person who
 * pressed a button at the bottom of a long form sees the message. A refusal about no one field
 * shows above the form, so the form's top is brought into view instead.
 */
export function useFocusFirstError(form: RefObject<HTMLFormElement | null>, error: Error | null) {
  useEffect(() => {
    if (error === null || form.current === null) {
      return
    }
    const firstInvalid = form.current.querySelector<HTMLElement>('[aria-invalid="true"]')
    if (firstInvalid !== null) {
      firstInvalid.focus()
      return
    }
    /* v8 ignore next -- jsdom has no layout, so it has no scrollIntoView to call */
    form.current.scrollIntoView?.({ block: 'start' })
  }, [error, form])
}
