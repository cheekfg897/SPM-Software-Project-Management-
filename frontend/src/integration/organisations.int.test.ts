import { register } from '@/features/auth/api'
import { createOrganisation, fetchOrganisations } from '@/features/organisations/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import {
  newOrganiser,
  refusal,
  signInAs,
  signInAsNewAttendee,
  staffAccount,
  uniqueEmail,
} from './backend'

/** A name no earlier run has used, since names are unique (ADR-0013). */
function uniqueName(): string {
  return `Integration organisation ${uniqueEmail('organisation')}`
}

function newOrganisation() {
  return {
    name: uniqueName(),
    contact_name: 'Integration Contact',
    contact_email: uniqueEmail('contact'),
  }
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-66 client organisations against the backend', () => {
  it('records an organisation for staff, trimmed, and lists it', async () => {
    await signInAs(staffAccount())
    const organisation = newOrganisation()

    const created = await createOrganisation({
      ...organisation,
      name: `  ${organisation.name}  `,
      contact_phone: '+65 6123 4567',
    })
    const listed = await fetchOrganisations()

    expect(created).toEqual({
      id: expect.any(Number) as number,
      ...organisation,
      contact_phone: '+65 6123 4567',
      created_at: expect.any(String) as string,
    })
    expect(listed).toContainEqual(created)
  })

  it('lists by name, not in the order they were recorded', async () => {
    await signInAs(staffAccount())
    const prefix = uniqueName()
    const recordedFirst = await createOrganisation({ ...newOrganisation(), name: `${prefix} b` })
    const recordedSecond = await createOrganisation({ ...newOrganisation(), name: `${prefix} a` })

    const listed = await fetchOrganisations()

    const ours = listed.filter((organisation) => organisation.name.startsWith(prefix))
    expect(ours.map((organisation) => organisation.id)).toEqual([
      recordedSecond.id,
      recordedFirst.id,
    ])
  })

  it('refuses a name already recorded (409)', async () => {
    await signInAs(staffAccount())
    const organisation = newOrganisation()
    await createOrganisation(organisation)

    const error = await refusal(createOrganisation({ ...organisation, contact_name: 'Other' }))

    expect(error).toMatchObject({
      status: 409,
      code: 'conflict',
      message: 'A client organisation with this name already exists.',
    })
  })

  it('names each field it refuses (400)', async () => {
    await signInAs(staffAccount())

    const error = await refusal(
      createOrganisation({
        ...newOrganisation(),
        name: '   ',
        // One @ and no spaces, which the mock once took, but no dot after the @.
        contact_email: 'weiling@bayfront',
        contact_phone: '12345',
      }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      name: ['Must not be blank.'],
      contact_email: ['Not a valid email address.'],
      contact_phone: [
        'Contact phone must have at least 7 digits and use only spaces, hyphens, brackets and a leading +.',
      ],
    })
  })

  it('refuses the list and recording without a token (401)', async () => {
    const listing = await refusal(fetchOrganisations())
    const recording = await refusal(createOrganisation(newOrganisation()))

    expect([listing.status, recording.status]).toEqual([401, 401])
  })

  it('refuses an Attendee (403): organisation details are not theirs', async () => {
    await signInAsNewAttendee()

    const error = await refusal(fetchOrganisations())

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it('refuses an Event Organiser too, even one linked to an organisation (403)', async () => {
    await signInAs(staffAccount())
    const organisation = await createOrganisation(newOrganisation())
    sendRequestsAs(null)
    const organiser = newOrganiser(organisation.id)
    await register(organiser)
    await signInAs({ email: organiser.email, password: organiser.password })

    const error = await refusal(fetchOrganisations())

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })
})
