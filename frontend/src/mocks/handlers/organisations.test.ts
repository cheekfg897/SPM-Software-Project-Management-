import { INTERNAL_ROLES, ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { ApiError, apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { server } from '../server'

import { MOCK_ACCOUNTS, MOCK_ORGANISATION_IDS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import { MOCK_ORGANISATIONS } from './organisationFixtures'

/**
 * The organisations mock stands in for backend/app/modules/organisations (SCRUM-66), so these
 * tests pin it to what its routes, schema and service answer.
 */

const ORGANISATIONS_URL = '/api/organisations'
const PHONE_RULE_MESSAGE =
  'Contact phone must have at least 7 digits and use only spaces, hyphens, brackets and a leading +.'

interface Listed {
  organisations: { id: number; name: string }[]
}

const STAFF_BY_ROLE: Partial<Record<Role, MockAccount>> = {
  [ROLE.EVENT_COORDINATOR]: MOCK_ACCOUNTS.coordinator,
  [ROLE.EVENT_COORDINATOR_LEAD]: MOCK_ACCOUNTS.lead,
  [ROLE.VENUE_STAFF]: MOCK_ACCOUNTS.venueStaff,
  [ROLE.TECHNICAL_SUPPORT_STAFF]: MOCK_ACCOUNTS.technicalSupport,
  [ROLE.SAFETY_OFFICER]: MOCK_ACCOUNTS.safetyOfficer,
}
const OUTSIDERS = [MOCK_ACCOUNTS.organiser, MOCK_ACCOUNTS.attendee]

function staffAccount(role: Role): MockAccount {
  const account = STAFF_BY_ROLE[role]
  if (account === undefined) {
    throw new Error(`No mock staff account for ${role}.`)
  }
  return account
}

function list() {
  return apiRequest<Listed>(ORGANISATIONS_URL)
}

function record(body: Record<string, unknown>) {
  return apiRequest<Record<string, unknown>>(ORGANISATIONS_URL, { method: 'POST', body })
}

function validOrganisation(overrides: Record<string, unknown> = {}) {
  return {
    name: 'Bayfront Partners',
    contact_name: 'Wei Ling Tan',
    contact_email: 'weiling@bayfront.test',
    ...overrides,
  }
}

async function errorOf(promise: Promise<unknown>): Promise<ApiError> {
  const error: unknown = await promise.then(
    () => null,
    (caught: unknown) => caught,
  )
  if (!(error instanceof ApiError)) {
    throw new Error('Expected the request to fail with an ApiError.')
  }
  return error
}

beforeEach(() => {
  sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.venueStaff))
})

describe('SCRUM-66 organisations mock: listing', () => {
  it('lists every organisation by name, inside an `organisations` key', async () => {
    const listed = await list()

    expect(listed.organisations.map((organisation) => organisation.id)).toEqual([3, 2, 1])
    expect(listed.organisations[0]).toEqual(MOCK_ORGANISATIONS[2])
  })

  it('starts with the organisations sign-up accepts, so the two mocks agree', () => {
    expect(MOCK_ORGANISATIONS.map((organisation) => organisation.id).sort()).toEqual([
      ...MOCK_ORGANISATION_IDS,
    ])
  })

  it.each(INTERNAL_ROLES)('lets %s list them', async (role) => {
    sendRequestsAs(mockTokenFor(staffAccount(role)))

    expect((await list()).organisations).toHaveLength(3)
  })

  it.each(OUTSIDERS)(
    'refuses $role (403): organisation details are not theirs',
    async (account) => {
      sendRequestsAs(mockTokenFor(account))

      const error = await errorOf(list())

      expect([error.status, error.code]).toEqual([403, 'authorization_error'])
    },
  )

  it('refuses a request without a token (401)', async () => {
    sendRequestsAs(null)

    expect((await errorOf(list())).status).toBe(401)
  })
})

describe('SCRUM-66 organisations mock: recording', () => {
  it('records an organisation with the next id, trimmed, and lists it in name order', async () => {
    const created = await record(
      validOrganisation({ name: '  Bayfront Partners ', contact_name: ' Wei Ling Tan ' }),
    )

    expect(created).toEqual({
      id: 4,
      name: 'Bayfront Partners',
      contact_name: 'Wei Ling Tan',
      contact_email: 'weiling@bayfront.test',
      contact_phone: null,
      created_at: expect.any(String) as string,
    })
    const names = (await list()).organisations.map((organisation) => organisation.name)
    expect(names).toEqual([
      'Acme Conferences',
      'Bayfront Partners',
      'Harbour Lights Ltd',
      'Orchid Events Co',
    ])
  })

  it('answers a recording with 201 Created', async () => {
    const statuses: number[] = []
    const onResponse = ({ response }: { response: Response }) => statuses.push(response.status)
    server.events.on('response:mocked', onResponse)

    await record(validOrganisation())

    server.events.removeListener('response:mocked', onResponse)
    expect(statuses).toEqual([201])
  })

  it('keeps a contact phone as typed, trimmed, and stores a blank one as none', async () => {
    const withPhone = await record(validOrganisation({ contact_phone: ' +65 (6) 123-4567 ' }))
    const blankPhone = await record(validOrganisation({ name: 'Other', contact_phone: '   ' }))

    expect(withPhone.contact_phone).toBe('+65 (6) 123-4567')
    expect(blankPhone.contact_phone).toBeNull()
  })

  it.each(INTERNAL_ROLES)('lets %s record one', async (role) => {
    sendRequestsAs(mockTokenFor(staffAccount(role)))

    expect((await record(validOrganisation())).name).toBe('Bayfront Partners')
  })

  it.each(OUTSIDERS)('refuses $role (403)', async (account) => {
    sendRequestsAs(mockTokenFor(account))

    expect((await errorOf(record(validOrganisation()))).status).toBe(403)
  })

  it('refuses a request without a token (401)', async () => {
    sendRequestsAs(null)

    expect((await errorOf(record(validOrganisation()))).status).toBe(401)
  })

  it('refuses a name already taken, even with spaces around it (409)', async () => {
    const error = await errorOf(record(validOrganisation({ name: '  Acme Conferences  ' })))

    expect([error.status, error.code, error.message]).toEqual([
      409,
      'conflict',
      'A client organisation with this name already exists.',
    ])
  })

  it('treats names that differ only in case as two organisations', async () => {
    const created = await record(validOrganisation({ name: 'acme conferences' }))

    expect(created.name).toBe('acme conferences')
  })

  it('names every missing required field', async () => {
    const error = await errorOf(record({}))

    expect(error.status).toBe(400)
    expect(error.fieldErrors).toEqual({
      name: ['Missing data for required field.'],
      contact_name: ['Missing data for required field.'],
      contact_email: ['Missing data for required field.'],
    })
  })

  it.each([
    ['name', { name: '   ' }, ['Must not be blank.']],
    ['name', { name: 'x'.repeat(121) }, ['Name must be at most 120 characters.']],
    [
      'name',
      { name: ' '.repeat(121) },
      ['Must not be blank.', 'Name must be at most 120 characters.'],
    ],
    ['name', { name: 5 }, ['Not a valid string.']],
    ['name', { name: null }, ['Field may not be null.']],
    ['contact_name', { contact_name: '  ' }, ['Must not be blank.']],
    [
      'contact_name',
      { contact_name: 'y'.repeat(121) },
      ['Contact name must be at most 120 characters.'],
    ],
    ['contact_email', { contact_email: 'nope' }, ['Not a valid email address.']],
    ['contact_email', { contact_email: 'two@at@signs.test' }, ['Not a valid email address.']],
    ['contact_email', { contact_email: 'wei ling@bayfront.test' }, ['Not a valid email address.']],
    [
      'contact_email',
      { contact_email: `${'a'.repeat(250)}@x.com` },
      ['Contact email must be at most 255 characters.'],
    ],
    ['contact_email', { contact_email: null }, ['Field may not be null.']],
    ['contact_email', { contact_email: 5 }, ['Not a valid email address.']],
    ['contact_email', { contact_email: '  ' }, ['Not a valid email address.']],
    [
      'contact_email',
      { contact_email: 'a'.repeat(260) },
      ['Not a valid email address.', 'Contact email must be at most 255 characters.'],
    ],
    ['contact_name', { contact_name: 5 }, ['Not a valid string.']],
    ['contact_name', { contact_name: null }, ['Field may not be null.']],
    ['contact_phone', { contact_phone: '123456' }, [PHONE_RULE_MESSAGE]],
    ['contact_phone', { contact_phone: '6123 4567 ext 2' }, [PHONE_RULE_MESSAGE]],
    ['contact_phone', { contact_phone: '65+61234567' }, [PHONE_RULE_MESSAGE]],
    ['contact_phone', { contact_phone: '++6561234567' }, [PHONE_RULE_MESSAGE]],
    [
      'contact_phone',
      { contact_phone: '1'.repeat(31) },
      ['Contact phone must be at most 30 characters.'],
    ],
    ['contact_phone', { contact_phone: 61234567 }, ['Not a valid string.']],
    ['website', { website: 'https://bayfront.test' }, ['Unknown field.']],
  ])('refuses %s in %j, saying why', async (field, overrides, messages) => {
    const error = await errorOf(record(validOrganisation(overrides)))

    expect(error.status).toBe(400)
    expect(error.fieldErrors).toEqual({ [field]: messages })
  })

  // Each one checked with marshmallow 4.3.1's Email, as the backend runs it.
  it.each([
    'weiling@bayfront',
    'weiling@bayfront.t',
    'weiling@bayfront.test.',
    'weiling@bayfront..test',
    'weiling@-bayfront.test',
    'weiling@bayfront-.test',
    'weiling@bay_front.test',
    '.weiling@bayfront.test',
    'weiling.@bayfront.test',
    'wei..ling@bayfront.test',
    'wei(ling)@bayfront.test',
  ])('refuses the email %j, as marshmallow does', async (email) => {
    const error = await errorOf(record(validOrganisation({ contact_email: email })))

    expect(error.fieldErrors).toEqual({ contact_email: ['Not a valid email address.'] })
  })

  it.each([
    "o'brien+events@bayfront.test",
    'wei.ling@mail.bay-front.test',
    'WEILING@BAYFRONT.TEST',
    'weiling@localhost',
  ])('accepts the email %j, as marshmallow does', async (email) => {
    const created = await record(validOrganisation({ contact_email: email }))

    expect(created.contact_email).toBe(email)
  })

  it.each([
    ['a name of exactly 120 characters', { name: 'n'.repeat(120) }],
    ['a contact name of exactly 120 characters', { contact_name: 'c'.repeat(120) }],
    ['an email of exactly 255 characters', { contact_email: `${'a'.repeat(249)}@x.com` }],
    ['a phone of exactly 7 digits', { contact_phone: '1234567' }],
    ['a phone of exactly 30 characters', { contact_phone: `+${'9'.repeat(29)}` }],
    ['every digit in a phone', { contact_phone: '0123456789' }],
    ['no phone at all', { contact_phone: null }],
  ])('accepts %s', async (_case, overrides) => {
    const created = await record(validOrganisation(overrides))

    expect(created.id).toBe(4)
  })
})
