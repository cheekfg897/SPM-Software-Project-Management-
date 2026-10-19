import { screen } from '@testing-library/react'

import { equipmentTypePath, ROUTES } from '@/config/routes'
import { MOCK_ACCOUNTS, mockSessionFor } from '@/mocks/fixtures/accounts'
import type { MockAccount } from '@/mocks/fixtures/accounts'
import { renderApp } from '@/test/render'

import { definitionsIn } from '../test/definitions'
import { OTHER_STAFF } from '../test/staff'

function openTypeAs(account: MockAccount, equipmentTypeId: number) {
  return renderApp(equipmentTypePath(equipmentTypeId), { session: mockSessionFor(account) })
}

/** The type's details, each label with its value. */
async function details() {
  await screen.findByText('Total quantity held')
  return definitionsIn(document.body)
}

describe('SCRUM-27 one equipment type', () => {
  it('shows the type under its name: description, total held and venue (AC2)', async () => {
    openTypeAs(MOCK_ACCOUNTS.venueStaff, 2)

    expect(await screen.findByRole('heading', { level: 1, name: 'Microphone' })).toBeInTheDocument()
    expect(await details()).toEqual({
      Description: 'Wireless, handheld.',
      'Total quantity held': '12',
      'Where it is kept': 'Venue 3',
    })
  })

  it('shows a type kept in a store, and says when it has no description', async () => {
    openTypeAs(MOCK_ACCOUNTS.coordinator, 3)

    expect(await screen.findByRole('heading', { level: 1, name: 'Lectern' })).toBeInTheDocument()
    expect(await details()).toEqual({
      Description: 'No description',
      'Total quantity held': '2',
      'Where it is kept': 'Store: Main store',
    })
  })

  it('offers Technical Support a link to edit it (AC1)', async () => {
    openTypeAs(MOCK_ACCOUNTS.technicalSupport, 2)

    expect(await screen.findByRole('link', { name: 'Edit' })).toHaveAttribute(
      'href',
      '/staff/equipment/2/edit',
    )
  })

  it.each(OTHER_STAFF)('offers %s no link to edit it (AC3)', async (_who, account) => {
    openTypeAs(account, 2)

    await screen.findByRole('heading', { level: 1, name: 'Microphone' })
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument()
  })

  it('links back to the whole catalogue', async () => {
    openTypeAs(MOCK_ACCOUNTS.coordinator, 2)

    expect(await screen.findByRole('link', { name: 'All equipment' })).toHaveAttribute(
      'href',
      ROUTES.EQUIPMENT_CATALOGUE,
    )
  })

  it('says what it is loading, under a heading that waits for the name', () => {
    openTypeAs(MOCK_ACCOUNTS.coordinator, 2)

    expect(screen.getByRole('status')).toHaveTextContent('Loading the equipment type')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Equipment type')
  })

  it("shows the backend's message for a type that does not exist", async () => {
    openTypeAs(MOCK_ACCOUNTS.coordinator, 999)

    expect(await screen.findByRole('alert')).toHaveTextContent('Equipment type not found.')
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument()
  })
})
