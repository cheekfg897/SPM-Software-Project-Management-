import { useParams } from 'react-router'

import { RecordQueryStatus } from '../components/RecordQueryStatus'
import { StaffEventRecordView } from '../components/StaffEventRecordView'
import { useStaffEventRecord } from '../hooks'

/**
 * Any submitted event's read-only record, for Venue Staff, Technical Support, the Safety Officer
 * and the Event Coordinator Lead (SCRUM-24 AC9, AC10; ADR-0095). A draft or an unknown event
 * gets the backend's "not found", shown as it comes.
 */
export function StaffEventPage() {
  // The route always supplies it; useParams just types it as possibly missing.
  const { reference = '' } = useParams()
  const record = useStaffEventRecord(reference)

  if (!record.isSuccess) {
    return <RecordQueryStatus query={record} />
  }
  return <StaffEventRecordView record={record.data} />
}
