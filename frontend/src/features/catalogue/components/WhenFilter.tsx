import { useState } from 'react'

import { SegmentedControl, TextField } from '@/components/ui'
import type { SegmentedOption } from '@/components/ui'
import { fieldErrorsOf } from '@/lib/api'

import { WHEN } from '../constants'
import type { When } from '../constants'
import { useCatalogue, useCatalogueParams } from '../hooks'
import { hasCustomRange } from '../searchParams'

/** Not a preset: the choice that shows the From and To inputs. It's never sent. */
const PICK_DATES = 'pick_dates'

const WHEN_OPTIONS: readonly SegmentedOption<string>[] = [
  { value: WHEN.UPCOMING, label: 'Upcoming' },
  { value: WHEN.TODAY, label: 'Today' },
  { value: WHEN.THIS_WEEK, label: 'This week' },
  { value: WHEN.THIS_WEEKEND, label: 'This weekend' },
  { value: PICK_DATES, label: 'Pick dates' },
]

const PRESETS: readonly string[] = Object.values(WHEN)

function isPreset(value: string): value is When {
  return PRESETS.includes(value)
}

/**
 * Choose a preset window or a custom range. Which dates a preset covers is the backend's
 * call, and so is whether a range is valid: its messages show under the inputs.
 */
export function WhenFilter() {
  const { params, choosePreset, setRangeEnd } = useCatalogueParams()
  const { error } = useCatalogue(params)
  const [isPickingDates, setIsPickingDates] = useState(false)
  const showsRange = isPickingDates || hasCustomRange(params)
  const selected = showsRange ? PICK_DATES : (params.when ?? WHEN.UPCOMING)
  const fieldErrors = fieldErrorsOf(error)

  function choose(value: string) {
    if (isPreset(value)) {
      setIsPickingDates(false)
      choosePreset(value)
      return
    }
    // "Pick dates": show the inputs, and drop any preset until a date is entered.
    setIsPickingDates(true)
    choosePreset(WHEN.UPCOMING)
  }

  return (
    <div className="space-y-4">
      <SegmentedControl label="When" options={WHEN_OPTIONS} value={selected} onChange={choose} />
      {showsRange && (
        <div className="grid gap-4 sm:max-w-xl sm:grid-cols-2">
          <TextField
            label="From"
            name="starts_from"
            type="datetime-local"
            value={params.starts_from ?? ''}
            onChange={(event) => setRangeEnd('starts_from', event.target.value)}
            errors={fieldErrors.starts_from}
          />
          <TextField
            label="To"
            name="starts_to"
            type="datetime-local"
            value={params.starts_to ?? ''}
            onChange={(event) => setRangeEnd('starts_to', event.target.value)}
            errors={fieldErrors.starts_to}
          />
        </div>
      )}
    </div>
  )
}
