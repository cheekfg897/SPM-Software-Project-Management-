import { attributed } from '@/lib/attributed'

import type { Clarification } from '../api'

/** One question, and the organiser's answer once they have given it. */
function ClarificationExchange({ clarification }: { clarification: Clarification }) {
  const { answered_at: answeredAt } = clarification
  return (
    <li className="border-line/60 bg-surface/50 rounded-2xl border p-5">
      <p className="text-ink">{clarification.message}</p>
      <p className="text-ink-faint mt-1 text-sm">
        {attributed('Asked', clarification.requested_by, clarification.requested_at)}
      </p>
      {answeredAt === null ? (
        <p className="text-flare mt-3 text-sm font-medium">Waiting for an answer.</p>
      ) : (
        <div className="border-line/60 mt-3 border-l-2 pl-4">
          <p className="text-ink">{clarification.response}</p>
          <p className="text-ink-faint mt-1 text-sm">
            {attributed('Answered', clarification.answered_by, answeredAt)}
          </p>
        </div>
      )}
    </li>
  )
}

/** Every clarification question in the order asked, each with its answer (SCRUM-32 AC4). */
export function ClarificationList({ clarifications }: { clarifications: Clarification[] }) {
  return (
    <ol className="space-y-3">
      {clarifications.map((clarification) => (
        <ClarificationExchange key={clarification.requested_at} clarification={clarification} />
      ))}
    </ol>
  )
}
