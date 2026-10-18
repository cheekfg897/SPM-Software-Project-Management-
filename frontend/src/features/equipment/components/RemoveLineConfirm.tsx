import { Button, ErrorAlert } from '@/components/ui'

import type { EquipmentLine } from '../api'
import { useRemoveEquipmentLine } from '../hooks'

interface RemoveLineConfirmProps {
  reference: string
  line: EquipmentLine
  lineName: string
  /** Close the question: once the line is removed, or kept. */
  onDone: () => void
}

/** Ask before removing a line (ADR-0065): a removal can't be undone and loses its notes. */
export function RemoveLineConfirm({ reference, line, lineName, onDone }: RemoveLineConfirmProps) {
  const remove = useRemoveEquipmentLine(reference)

  return (
    <div className="border-danger/40 bg-surface/70 space-y-4 rounded-2xl border p-5">
      <ErrorAlert error={remove.error} />
      <p className="font-display text-lg font-semibold tracking-tight">
        Remove {lineName} from this event?
      </p>
      <p className="text-ink-muted text-sm">
        Technical Support will no longer see it, and its notes are lost.
      </p>
      <div className="flex flex-wrap gap-3">
        <Button
          isPending={remove.isPending}
          onClick={() => remove.mutate(line.id, { onSuccess: onDone })}
        >
          Remove line
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Keep it
        </Button>
      </div>
    </div>
  )
}
