import { screen, within } from '@testing-library/react'

import { STAFF_RECORD_READER_ROLES } from '@/config/roles'
import { eventEquipmentPath, ROUTES, staffEventPath } from '@/config/routes'
import { homeFor } from '@/features/auth/roleHome'
import { reserveEquipment } from '@/features/equipment/api'
import { editEventRequest } from '@/features/eventRequests/api'
import { MOCK_ACCOUNTS, mockSessionFor, mockTokenFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { recordRequests } from '@/test/recordRequests'
import { renderApp } from '@/test/render'
import { sendRequestsAs } from '@/test/sendRequestsAs'

/**
 * SCRUM-24 AC9, AC10: Venue Staff, Technical Support, the Safety Officer and the Event
 * Coordinator Lead open any submitted event's record, read-only (ADR-0095), with its venue and
 * equipment preparation (SCRUM-84 AC2, SCRUM-85 AC2) and its history (SCRUM-33 AC5). The records
 * come from the mock in src/mocks/handlers/staffEventRecord.ts: EVR-7K2M9QXA is Chloe's Partner
 * Summit, EVR-BOOK0110 the booking mock's event being prepared, EVR-MOCK0001 Chloe's event with
 * two equipment lines, and EVR-SAFE0004 an event the Safety Officer approved.
 */

const PARTNER_SUMMIT = 'EVR-7K2M9QXA'
const BEING_PREPARED = 'EVR-BOOK0110'
const WITH_EQUIPMENT = 'EVR-MOCK0001'
const SAFETY_APPROVED = 'EVR-SAFE0004'
const LOADING_TEXT = 'Loading the event…'

/** One mock account of each reader role. */
const READERS = [
  ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
  ['Technical Support', MOCK_ACCOUNTS.technicalSupport],
  ['the Safety Officer', MOCK_ACCOUNTS.safetyOfficer],
  ['the Event Coordinator Lead', MOCK_ACCOUNTS.lead],
] as const

function openAs(account: MockAccount, reference: string) {
  return renderApp(staffEventPath(reference), { session: mockSessionFor(account) })
}

/** The section headed `name`, once the record has loaded. */
async function section(name: string): Promise<HTMLElement> {
  const heading = await screen.findByRole('heading', { level: 2, name })
  const found = heading.closest('section')
  if (found === null) {
    throw new Error(`No section is headed "${name}"`)
  }
  return found
}

describe('SCRUM-24 AC9, AC10 the read-only staff record', () => {
  it('opens to each of the four roles, and the readers tried are all four', async () => {
    expect(READERS.map(([, account]) => account.role).sort()).toEqual(
      [...STAFF_RECORD_READER_ROLES].sort(),
    )
    for (const [, account] of READERS) {
      const { unmount } = openAs(account, PARTNER_SUMMIT)

      expect(
        await screen.findByRole('heading', { level: 1, name: 'Partner Summit' }),
      ).toBeInTheDocument()
      unmount()
    }
  })

  it('heads the page with the event, its status, reference and when it is on', async () => {
    openAs(MOCK_ACCOUNTS.lead, PARTNER_SUMMIT)

    expect(await screen.findByText('Thu, 12 Nov · 9:00 am – 5:00 pm')).toBeInTheDocument()
    expect(screen.getByText('Under review')).toBeInTheDocument()
    expect(screen.getByText(PARTNER_SUMMIT)).toBeInTheDocument()
  })

  it('says it is loading until the record arrives', async () => {
    openAs(MOCK_ACCOUNTS.venueStaff, PARTNER_SUMMIT)

    expect(screen.getByText(LOADING_TEXT)).toBeInTheDocument()
    await screen.findByRole('heading', { level: 1, name: 'Partner Summit' })
    expect(screen.queryByText(LOADING_TEXT)).not.toBeInTheDocument()
  })

  it("shows the backend's own words when the record can't be opened", async () => {
    openAs(MOCK_ACCOUNTS.lead, 'EVR-H2PL8R6K')

    expect(await screen.findByText('Event request not found.')).toBeInTheDocument()
  })

  it('shows the details, the coordinator, the programme notes and the history', async () => {
    openAs(MOCK_ACCOUNTS.safetyOfficer, PARTNER_SUMMIT)

    const about = await section('About the event')
    expect(within(about).getByText('Venue requirements').nextElementSibling).toHaveTextContent(
      'A main hall for 250 and four breakout rooms.',
    )
    expect(await section('Coordinator')).toHaveTextContent('Chloe Lim · chloe@connectsphere.test')
    expect(await section('Programme notes')).toHaveTextContent(
      'Keynote at 9:30, breakout rooms after lunch.',
    )
    expect(await section('History')).toBeInTheDocument()
  })

  it('shows the internal planning notes the coordinator saved', async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
    await editEventRequest(PARTNER_SUMMIT, { internal_planning_notes: 'Client prefers mornings.' })
    sendRequestsAs(null)
    openAs(MOCK_ACCOUNTS.venueStaff, PARTNER_SUMMIT)

    expect(await section('Internal planning notes')).toHaveTextContent('Client prefers mornings.')
  })

  it('says when there are no internal planning notes yet', async () => {
    openAs(MOCK_ACCOUNTS.venueStaff, PARTNER_SUMMIT)

    expect(await section('Internal planning notes')).toHaveTextContent(
      'No internal planning notes yet.',
    )
  })

  it("shows each venue arrangement with Venue Staff's preparation (SCRUM-84 AC2)", async () => {
    openAs(MOCK_ACCOUNTS.lead, BEING_PREPARED)

    const venues = await section('Venue arrangements')
    expect(venues).toHaveTextContent('Marina Hall')
    expect(venues).toHaveTextContent('12 Nov, 9:00 am – 5:00 pm · Approved')
    expect(venues).toHaveTextContent('Preparation: In progress')
    expect(venues).toHaveTextContent('Preparation notes: Stage half built.')
  })

  it('says when no venue is arranged and no equipment requested or reserved', async () => {
    openAs(MOCK_ACCOUNTS.lead, PARTNER_SUMMIT)

    expect(await section('Venue arrangements')).toHaveTextContent(
      'No venue is arranged for this event yet.',
    )
    const equipment = await section('Equipment')
    expect(equipment).toHaveTextContent('No equipment has been requested for this event.')
    expect(equipment).toHaveTextContent('No equipment is reserved for this event yet.')
  })

  it("shows the equipment requested with Technical Support's outcome, and each reservation's preparation (SCRUM-85 AC2)", async () => {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.technicalSupport))
    await reserveEquipment(WITH_EQUIPMENT, { equipment_type_id: 2, quantity: 4 })
    sendRequestsAs(null)
    openAs(MOCK_ACCOUNTS.venueStaff, WITH_EQUIPMENT)

    const equipment = await section('Equipment')
    const requested = within(equipment).getByRole('list', { name: 'Equipment requested' })
    const lines = within(requested).getAllByRole('listitem')
    expect(lines[0]).toHaveTextContent('Projector · 8 requested')
    expect(lines[0]).toHaveTextContent('Note: Ceiling-mounted, with HDMI at the lectern.')
    expect(lines[0]).toHaveTextContent('Technical Support: Awaiting Technical Support')
    expect(lines[1]).toHaveTextContent('Technical Support: Fulfilled, 4 provided')
    const reserved = within(equipment).getByRole('list', { name: 'Equipment reserved' })
    expect(reserved).toHaveTextContent('Microphone · 4 reserved')
    expect(reserved).toHaveTextContent('by Tariq Hassan')
    expect(reserved).toHaveTextContent('Preparation: Not started')
  })

  it("shows the Safety Officer's outcome with each checklist note", async () => {
    openAs(MOCK_ACCOUNTS.venueStaff, SAFETY_APPROVED)

    const safety = await section('Safety check')
    expect(within(safety).getByText('Approved')).toBeInTheDocument()
    expect(within(safety).getByText('Emergency access').nextElementSibling).toHaveTextContent(
      'Exits kept clear.',
    )
    expect(safety).toHaveTextContent('Recorded by Sana Iyer')
  })

  it('shows the reason the Safety Officer gave for an outcome other than approval', async () => {
    openAs(MOCK_ACCOUNTS.lead, 'EVR-SAFE0005')

    const safety = await section('Safety check')
    expect(within(safety).getByText('Changes requested')).toBeInTheDocument()
    expect(within(safety).getByText('Add a second fire exit to the plan.')).toBeInTheDocument()
  })

  it("shows the coordinator's decision and the clarification exchange, as their record does", async () => {
    const { unmount } = openAs(MOCK_ACCOUNTS.venueStaff, 'EVR-W9CR5E7M')
    expect(await section('Decision')).toHaveTextContent('Approved')
    unmount()

    openAs(MOCK_ACCOUNTS.venueStaff, 'EVR-B6YF2K8V')

    expect(await section('Clarifications')).toHaveTextContent(
      'Can the start move to 2pm so the vans can unload first?',
    )
  })

  it('says when the current safety check has no outcome yet', async () => {
    openAs(MOCK_ACCOUNTS.venueStaff, PARTNER_SUMMIT)

    expect(await section('Safety check')).toHaveTextContent(
      "The Safety Officer hasn't recorded an outcome on the current check.",
    )
  })

  it('has no actions, no planning links and no registrants', async () => {
    openAs(MOCK_ACCOUNTS.lead, PARTNER_SUMMIT)

    await section('History')
    const main = screen.getByRole('main')
    expect(within(main).queryAllByRole('button')).toEqual([])
    expect(within(main).queryByRole('link', { name: 'Venue requests' })).not.toBeInTheDocument()
    expect(within(main).queryByRole('link', { name: 'Equipment' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Registrants' })).not.toBeInTheDocument()
  })

  it("links Technical Support on to the event's Equipment page, where they work on it", async () => {
    const { user, router } = openAs(MOCK_ACCOUNTS.technicalSupport, WITH_EQUIPMENT)

    await section('About the event')
    await user.click(within(screen.getByRole('main')).getByRole('link', { name: 'Equipment' }))

    expect(router.state.location.pathname).toBe(eventEquipmentPath(WITH_EQUIPMENT))
  })

  it.each([
    ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
    ['an Event Organiser', MOCK_ACCOUNTS.organiser],
    ['an Attendee', MOCK_ACCOUNTS.attendee],
  ])('sends %s to their own home instead, and asks for no record', async (_role, account) => {
    const requests = recordRequests()
    const { router } = openAs(account, PARTNER_SUMMIT)

    expect(router.state.location.pathname).toBe(homeFor(account.role))
    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument()
    const asked = requests.map((request) => new URL(request.url).pathname)
    expect(asked).not.toContain(`/api/events/requests/${PARTNER_SUMMIT}/staff-record`)
  })

  it('sends a visitor who is not signed in to the staff log-in', () => {
    const { router } = renderApp(staffEventPath(PARTNER_SUMMIT))

    expect(router.state.location.pathname).toBe(ROUTES.STAFF_LOGIN)
  })
})
