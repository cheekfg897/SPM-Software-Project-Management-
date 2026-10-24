import { useParams } from 'react-router'

import { EventRecordView } from '../components/EventRecordView'
import { RecordQueryStatus } from '../components/RecordQueryStatus'
import { useEventRequest } from '../hooks'

/**
 * One event's record, for an organiser of its organisation or its assigned coordinator, each
 * at their own address (SCRUM-24 AC9, AC10; ADR-0056). Anyone else gets the backend's "not
 * found", shown as it comes.
 */
export function EventRequestPage() {
  // The route always supplies it; useParams just types it as possibly missing.
  const { reference = '' } = useParams()
  const record = useEventRequest(reference)

  if (!record.isSuccess) {
    return <RecordQueryStatus query={record} />
  }
  return <EventRecordView record={record.data} />
}
